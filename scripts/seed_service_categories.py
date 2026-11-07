"""Bring the service categories and services in line with DEVTech's catalog.

This used to create its own set of nine categories under different slugs,
which duplicated the categories the site already had. It now runs the one
catalog definition in services/service_catalog.py, which renames and updates
existing records in place and never adds duplicates. Same as:

    flask --app app sync-service-catalog

Usage:
    python -m scripts.seed_service_categories
"""
from app import app, db, ServiceCategory, Service
from services.service_catalog import sync_service_catalog


def main():
    with app.app_context():
        changes = sync_service_catalog(db, ServiceCategory, Service)
        print('\n'.join(changes) if changes else 'Service catalog already up to date.')


if __name__ == '__main__':
    main()
