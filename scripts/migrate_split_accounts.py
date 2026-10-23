"""Convert an old single-`users`-table DEVTech database to separate
`customers`, `technicians` and `admins` tables.

Copy into a new database (the source is only read):

    python -m scripts.migrate_split_accounts \
        --source mysql+pymysql://root@127.0.0.1:3307/devtech_db \
        --target mysql+pymysql://root@127.0.0.1:3307/devtech

Or convert a database in place, keeping its name:

    python -m scripts.migrate_split_accounts --in-place \
        --source mysql+pymysql://root:PASSWORD@127.0.0.1:3306/devtech_db

  In place, the new tables are built in a staging database and then swapped in
  with one atomic RENAME TABLE. The old tables are not deleted: they move to
  `<name>_before_split` on the same server (plus the mysqldump backup).

What it does:
  1. Dumps the source database to instance/backups/ (mysqldump).
  2. Creates the target database (refuses if it already has tables, unless --replace).
  3. Creates every table from the current models.
  4. Copies all rows. users -> customers/technicians/admins by role, keeping
     each account's id; user_id -> customer_id on customer-owned tables; and
     notifications/messages/activity logs get the owner's role recorded.
  5. Prints row counts for both sides.
"""
import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent.parent
# Tables whose owner column was users.id and is now customers.id.
CUSTOMER_OWNED = {'bookings', 'transactions', 'orders', 'shopping_carts', 'support_tickets', 'user_preferences'}
ACCOUNT_TABLES = {'customers': 'customer', 'technicians': 'technician', 'admins': 'admin'}
# Role values seen in older databases -> account table role.
ROLE_ALIASES = {'customer': 'customer', 'user': 'customer', 'client': 'customer',
                'technician': 'technician', 'tech': 'technician', 'admin': 'admin', 'administrator': 'admin'}


def find_mysqldump():
    found = shutil.which('mysqldump')
    if found:
        return found
    for path in sorted(Path('C:/laragon/bin/mysql').glob('*/bin/mysqldump.exe'), reverse=True):
        return str(path)
    return None


def backup(source_url):
    url = make_url(source_url)
    exe = find_mysqldump()
    if not exe:
        sys.exit('mysqldump not found; back up the source database manually, then rerun with --no-backup.')
    out_dir = ROOT / 'instance' / 'backups'
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f'{url.database}_before_account_split_{datetime.now():%Y%m%d_%H%M%S}.sql'
    cmd = [exe, f'--host={url.host or "127.0.0.1"}', f'--port={url.port or 3306}',
           f'--user={url.username or "root"}', '--single-transaction', '--routines', url.database]
    env = dict(os.environ, MYSQL_PWD=url.password or '')
    with open(out, 'wb') as fh:
        subprocess.run(cmd, stdout=fh, check=True, env=env)
    print(f'Backup written: {out}')


def create_database(target_url, replace):
    url = make_url(target_url)
    server = create_engine(url.set(database='information_schema'))
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE IF NOT EXISTS `{url.database}` '
                          'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    engine = create_engine(url)
    existing = inspect(engine).get_table_names()
    if existing:
        if not replace:
            sys.exit(f'{url.database} already has {len(existing)} tables. Rerun with --replace to rebuild it.')
        with engine.begin() as conn:
            conn.execute(text('SET FOREIGN_KEY_CHECKS=0'))
            for name in existing:
                conn.execute(text(f'DROP TABLE `{name}`'))
            conn.execute(text('SET FOREIGN_KEY_CHECKS=1'))
    return engine


def load_models(target_url):
    os.environ['DATABASE_URL'] = target_url
    sys.path.insert(0, str(ROOT))
    import app as app_module                    # noqa: E402  (needs DATABASE_URL first)
    import models.technician_models             # noqa: F401,E402  registers the tech tables
    return app_module.db.metadata


def rows_of(conn, table):
    return [dict(r._mapping) for r in conn.execute(text(f'SELECT * FROM `{table}`'))]


def migrate(source_url, target_url, replace=False, do_backup=True):
    if do_backup:
        backup(source_url)
    target = create_database(target_url, replace)
    metadata = load_models(target_url)
    metadata.create_all(target)

    source = create_engine(source_url)
    source_tables = set(inspect(source).get_table_names())
    counts = []
    with source.connect() as src, target.begin() as dst:
        dst.execute(text('SET FOREIGN_KEY_CHECKS=0'))
        users = rows_of(src, 'users') if 'users' in source_tables else []
        unknown = sorted({str(u.get('role')) for u in users
                          if ROLE_ALIASES.get(str(u.get('role') or '').strip().lower()) is None})
        if unknown:
            sys.exit(f'users has roles this script does not know: {", ".join(unknown)}. Nothing was changed.')
        for u in users:
            u['role'] = ROLE_ALIASES[str(u['role']).strip().lower()]
        role_of = {u['id']: u['role'] for u in users}

        for table in metadata.sorted_tables:
            columns = {c.name for c in table.columns}
            if table.name in ACCOUNT_TABLES:
                rows = [u for u in users if u['role'] == ACCOUNT_TABLES[table.name]]
                source_name = f"users (role={ACCOUNT_TABLES[table.name]})"
            elif table.name in source_tables:
                rows = rows_of(src, table.name)
                source_name = table.name
            else:
                counts.append((table.name, '-', 0))
                continue

            out = []
            for row in rows:
                row = dict(row)
                if table.name in CUSTOMER_OWNED and 'user_id' in row:
                    row['customer_id'] = row.pop('user_id')
                if table.name in ('notifications', 'activity_logs'):
                    row['user_role'] = role_of.get(row.get('user_id'))
                if table.name == 'notifications' and row['user_role'] is None:
                    continue                    # owner no longer exists
                if table.name == 'messages':
                    row['sender_role'] = role_of.get(row['sender_id'])
                    row['recipient_role'] = role_of.get(row['recipient_id'])
                    if not row['sender_role'] or not row['recipient_role']:
                        continue
                out.append({k: v for k, v in row.items() if k in columns})
            if out:
                dst.execute(table.insert(), out)
            counts.append((table.name, f'{len(rows)} from {source_name}', len(out)))
        dst.execute(text('SET FOREIGN_KEY_CHECKS=1'))

    leftover = sorted(source_tables - {t.name for t in metadata.sorted_tables} - {'users'})
    print(f'\n{"table":<26} {"source":<34} copied')
    for name, src_desc, n in counts:
        print(f'{name:<26} {src_desc:<34} {n}')
    if leftover:
        with source.connect() as src:
            sizes = {t: src.execute(text(f'SELECT COUNT(*) FROM `{t}`')).scalar() for t in leftover}
        print('\nSource tables the app no longer uses (not copied; kept in the backup):')
        for t in leftover:
            print(f'  {t:<24} {sizes[t]} row(s)')
    source.dispose()
    target.dispose()


def swap_in(source_url, staging_url):
    """Move the source's tables to <source>_before_split and the staging tables
    into the source database, in one atomic RENAME TABLE."""
    src_db = make_url(source_url).database
    stg_db = make_url(staging_url).database
    legacy = f'{src_db}_before_split'
    server = create_engine(make_url(source_url).set(database='information_schema'))
    with server.begin() as conn:
        def tables(db):
            return [r[0] for r in conn.execute(text(
                'SELECT TABLE_NAME FROM information_schema.TABLES '
                "WHERE TABLE_SCHEMA = :db AND TABLE_TYPE = 'BASE TABLE'"), {'db': db})]
        if tables(legacy):
            sys.exit(f'{legacy} already has tables; rename or drop it first. {src_db} was not changed.')
        old, new = tables(src_db), tables(stg_db)
        conn.execute(text(f'CREATE DATABASE IF NOT EXISTS `{legacy}` '
                          'CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
        pairs = [f'`{src_db}`.`{t}` TO `{legacy}`.`{t}`' for t in old] + \
                [f'`{stg_db}`.`{t}` TO `{src_db}`.`{t}`' for t in new]
        conn.execute(text('RENAME TABLE ' + ', '.join(pairs)))
        conn.execute(text(f'DROP DATABASE `{stg_db}`'))
    server.dispose()
    print(f'\n{src_db} now has the new tables. The old ones are in {legacy}.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', required=True, help='old database URL (single users table)')
    p.add_argument('--target', help='new database URL (created if missing)')
    p.add_argument('--in-place', action='store_true', help='convert the source database itself, keeping its name')
    p.add_argument('--replace', action='store_true', help='drop and rebuild the target if it has tables')
    p.add_argument('--no-backup', action='store_true', help='skip the mysqldump backup of the source')
    a = p.parse_args()
    if a.in_place == bool(a.target):
        p.error('give either --target or --in-place')
    if a.in_place:
        src = make_url(a.source)
        staging = src.set(database=f'{src.database}_split_staging').render_as_string(hide_password=False)
        migrate(a.source, staging, replace=True, do_backup=not a.no_backup)
        swap_in(a.source, staging)
        print(f'Point DATABASE_URL at {src.render_as_string(hide_password=True)}')
    else:
        migrate(a.source, a.target, replace=a.replace, do_backup=not a.no_backup)
        print(f'\nDone. Point DATABASE_URL at {make_url(a.target).render_as_string(hide_password=True)}')
