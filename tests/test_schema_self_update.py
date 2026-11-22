"""Vercel never runs `flask upgrade-db`: the site brings the database up to the code on
its own, so a column added in an update can't turn the home page into a 500."""
from sqlalchemy import text, inspect

from app import app as flask_app, db, ensure_schema


def _columns(table):
    return {c['name'] for c in inspect(db.engine).get_columns(table)}


def test_missing_columns_and_tables_are_added_and_the_home_page_works(client):
    # The live database as it was before this update: no back-of-ID column, no nav_seen table.
    db.session.execute(text('ALTER TABLE technicians DROP COLUMN id_back_file'))
    db.session.execute(text('DROP TABLE nav_seen'))
    db.session.commit()
    assert 'id_back_file' not in _columns('technicians')

    added = ensure_schema()
    assert 'technicians.id_back_file' in added and 'table nav_seen' in added
    assert 'id_back_file' in _columns('technicians') and 'nav_seen' in inspect(db.engine).get_table_names()
    assert client.get('/').status_code == 200
    assert ensure_schema() == []                      # nothing left to do the second time


def test_every_column_type_can_be_added_on_postgresql_and_mysql():
    from sqlalchemy.dialects import postgresql, mysql
    for dialect in (postgresql.dialect(), mysql.dialect()):
        for table in db.metadata.tables.values():
            for col in table.columns:
                assert col.type.compile(dialect=dialect)
