"""Flask CLI commands for admin management.

Registered by app.py as `flask <command>`. Run with `flask --app app <cmd>`
or, if you've set `FLASK_APP=app.py` in .env, just `flask <cmd>`.

These are deliberately CLI-only — never HTTP routes. Anyone who can run
them already has shell access to the server, so they're not a new attack
surface; they replace the far worse pattern of a hardcoded admin sitting
in the source tree.

Admins live in their own `admins` table (customers and technicians have
their own tables too), so an account can't be "promoted" — create a
separate admin account instead.

The imports below are deferred inside register_commands because app.py
imports `register_commands` from this file; importing app at module load
would create a cycle.
"""
from getpass import getpass

import click


def _read_new_password(label='Password'):
    password = getpass(f'{label} (min 8 chars): ')
    confirm = getpass('Confirm password: ')
    if password != confirm:
        click.echo('Passwords do not match.', err=True)
        raise SystemExit(1)
    if len(password) < 8:
        click.echo('Password must be at least 8 characters.', err=True)
        raise SystemExit(1)
    return password


def register_commands(app):
    """Attach every CLI command to the Flask app. Called once from
    app.py at module load time, after `db` and the models already exist."""

    # Pull in models lazily so the module can be imported safely.
    from app import db, Admin, email_in_use

    # ----------------------------------------------------------------
    # CREATE-ADMIN
    # ----------------------------------------------------------------
    @app.cli.command('create-admin')
    @click.option('--email', prompt='Email', help='Admin email address')
    @click.option('--name', prompt='Full name', help='Admin full name')
    def create_admin(email, name):
        """Create a new admin account.

        Password is prompted interactively and never echoed to the
        terminal, so it does not end up in your shell history.
        """
        email = email.strip().lower()
        name = name.strip()

        if not email or '@' not in email:
            click.echo('That does not look like a valid email.', err=True)
            raise SystemExit(1)

        if email_in_use(email):
            click.echo(f'{email} is already registered.', err=True)
            raise SystemExit(1)

        password = _read_new_password()

        # Build a username from the email. Disambiguate on collision.
        username = email.split('@')[0]
        if Admin.query.filter_by(username=username).first():
            import secrets as _s
            username = f'{username}_{_s.token_hex(3)}'

        admin = Admin(username=username, email=email, full_name=name, is_active=True)
        admin.set_password(password)
        db.session.add(admin)

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            click.echo(f'Could not create admin: {exc}', err=True)
            raise SystemExit(1)

        click.echo(f'Created admin {name} <{email}>.')
        click.echo('Sign in at /admin/login')

    # ----------------------------------------------------------------
    # DEACTIVATE-ADMIN / ACTIVATE-ADMIN
    # ----------------------------------------------------------------
    @app.cli.command('deactivate-admin')
    @click.argument('email')
    def deactivate_admin(email):
        """Block an admin from signing in.

        Refuses if they are the last active admin, because that would
        lock you out of the panel entirely. Create another admin first.
        """
        admin = Admin.query.filter_by(email=email.strip().lower()).first()
        if not admin:
            click.echo(f'No admin with email {email}', err=True)
            raise SystemExit(1)
        if not admin.is_active:
            click.echo(f'{admin.email} is already inactive.')
            return
        if Admin.query.filter_by(is_active=True).count() <= 1:
            click.echo('Refusing: this is the last active admin. '
                       'Create another admin first, then try again.', err=True)
            raise SystemExit(1)
        admin.is_active = False
        db.session.commit()
        click.echo(f'Deactivated {admin.full_name} <{admin.email}>.')

    @app.cli.command('activate-admin')
    @click.argument('email')
    def activate_admin(email):
        """Let a deactivated admin sign in again."""
        admin = Admin.query.filter_by(email=email.strip().lower()).first()
        if not admin:
            click.echo(f'No admin with email {email}', err=True)
            raise SystemExit(1)
        admin.is_active = True
        db.session.commit()
        click.echo(f'Activated {admin.full_name} <{admin.email}>.')

    # ----------------------------------------------------------------
    # LIST-ADMINS
    # ----------------------------------------------------------------
    @app.cli.command('list-admins')
    def list_admins():
        """List every admin account and its status."""
        admins = Admin.query.order_by(Admin.created_at).all()

        if not admins:
            click.echo('No admins configured.')
            click.echo('Create one with:  flask --app app create-admin')
            return

        click.echo(f'{"Email":<40} {"Name":<30} {"Status":<10}')
        click.echo('-' * 82)
        for a in admins:
            status = 'active' if a.is_active else 'INACTIVE'
            click.echo(f'{a.email:<40} {(a.full_name or ""):<30} {status:<10}')

    # ----------------------------------------------------------------
    # UPGRADE-DB
    # ----------------------------------------------------------------
    @app.cli.command('upgrade-db')
    def upgrade_db():
        """Bring an existing database up to date: create new tables, add
        new columns, and run one-time data fixes. Never seeds demo data.
        Safe to run on every deploy."""
        import app as app_module
        db.create_all()
        for patch in ('update_payment_method_column', 'add_receipt_image_column',
                      'add_service_category_columns', 'add_profile_columns'):
            getattr(app_module, patch)()
        app_module.move_legacy_receipts()
        released = app_module.release_reserved_cart_stock()
        if released:
            click.echo(f'Returned {released} unit(s) held in open carts to product stock.')
        click.echo('Database is up to date.')

    # ----------------------------------------------------------------
    # RELEASE-CART-STOCK
    # ----------------------------------------------------------------
    @app.cli.command('release-cart-stock')
    def release_cart_stock():
        """One-time fix: return stock that open carts were holding under the
        old add-to-cart reservation model. Safe to run more than once."""
        from app import release_reserved_cart_stock
        released = release_reserved_cart_stock()
        if released is None:
            click.echo('Already done; nothing to release.')
        else:
            click.echo(f'Returned {released} unit(s) to product stock.')

    # ----------------------------------------------------------------
    # RESET-ADMIN-PASSWORD
    # ----------------------------------------------------------------
    @app.cli.command('reset-admin-password')
    @click.argument('email')
    def reset_admin_password(email):
        """Reset an admin's password. Useful when the setup flow did not
        run, or when you have locked yourself out.
        """
        email = email.strip().lower()
        admin = Admin.query.filter_by(email=email).first()

        if not admin:
            click.echo(f'No admin with email {email}', err=True)
            raise SystemExit(1)

        admin.set_password(_read_new_password('New password'))
        db.session.commit()
        click.echo(f'Password updated for {admin.full_name} <{email}>.')
