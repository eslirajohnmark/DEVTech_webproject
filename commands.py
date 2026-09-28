"""Flask CLI commands for admin management.

Registered by app.py as `flask <command>`. Run with `flask --app app <cmd>`
or, if you've set `FLASK_APP=app.py` in .env, just `flask <cmd>`.

These are deliberately CLI-only — never HTTP routes. Anyone who can run
them already has shell access to the server, so they're not a new attack
surface; they replace the far worse pattern of a hardcoded admin sitting
in the source tree.

The imports below are deferred inside each command function where they'd
otherwise create a circular dependency at module load. Specifically,
this file imports `app`, `db`, and `User` from app.py — and app.py
imports `register_commands` from this file. Keeping the heavy imports
deferred to call time breaks the cycle.
"""
from getpass import getpass

import click


def register_commands(app):
    """Attach every CLI command to the Flask app. Called once from
    app.py at module load time, after `db`, `User`, and the other
    models already exist."""

    # Pull in models lazily so the module can be imported safely.
    from app import db, User

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

        if User.query.filter_by(email=email).first():
            click.echo(f'{email} is already registered.', err=True)
            raise SystemExit(1)

        password = getpass('Password (min 8 chars): ')
        confirm = getpass('Confirm password: ')

        if password != confirm:
            click.echo('Passwords do not match.', err=True)
            raise SystemExit(1)
        if len(password) < 8:
            click.echo('Password must be at least 8 characters.', err=True)
            raise SystemExit(1)

        # Build a username from the email. Disambiguate on collision.
        username = email.split('@')[0]
        if User.query.filter_by(username=username).first():
            import secrets as _s
            username = f'{username}_{_s.token_hex(3)}'

        user = User(
            username=username,
            email=email,
            full_name=name,
            role='admin',
            is_active=True,
        )
        user.set_password(password)
        db.session.add(user)

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            click.echo(f'Could not create admin: {exc}', err=True)
            raise SystemExit(1)

        click.echo(f'Created admin {name} <{email}>.')
        click.echo('Sign in at /admin/login')

    # ----------------------------------------------------------------
    # PROMOTE-ADMIN
    # ----------------------------------------------------------------
    @app.cli.command('promote-admin')
    @click.argument('email')
    def promote_admin(email):
        """Promote an existing user to admin by email.

        Use this when you already have a customer or technician account
        and want to grant it admin rights without creating a new row.
        """
        email = email.strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user:
            click.echo(f'No user with email {email}', err=True)
            raise SystemExit(1)

        if user.role == 'admin':
            click.echo(f'{email} is already an admin.')
            return

        user.role = 'admin'
        user.is_active = True
        db.session.commit()
        click.echo(f'Promoted {user.full_name} <{email}> to admin.')

    # ----------------------------------------------------------------
    # DEMOTE-ADMIN
    # ----------------------------------------------------------------
    @app.cli.command('demote-admin')
    @click.argument('email')
    def demote_admin(email):
        """Demote an admin back to customer.

        Refuses if they are the last active admin, because that would
        lock you out of the panel entirely. Create another admin first.
        """
        email = email.strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user:
            click.echo(f'No user with email {email}', err=True)
            raise SystemExit(1)

        if user.role != 'admin':
            click.echo(f'{email} is not an admin.')
            return

        admin_count = User.query.filter_by(
            role='admin', is_active=True
        ).count()

        if admin_count <= 1:
            click.echo(
                'Refusing: this is the last active admin. '
                'Create another admin first, then try again.',
                err=True,
            )
            raise SystemExit(1)

        user.role = 'customer'
        db.session.commit()
        click.echo(f'Demoted {user.full_name} <{email}> to customer.')

    # ----------------------------------------------------------------
    # LIST-ADMINS
    # ----------------------------------------------------------------
    @app.cli.command('list-admins')
    def list_admins():
        """List every admin account and its status."""
        admins = User.query.filter_by(role='admin') \
            .order_by(User.created_at).all()

        if not admins:
            click.echo('No admins configured.')
            click.echo('Create one with:  flask --app app create-admin')
            return

        click.echo(f'{"Email":<40} {"Name":<30} {"Status":<10}')
        click.echo('-' * 82)
        for u in admins:
            status = 'active' if u.is_active else 'INACTIVE'
            click.echo(f'{u.email:<40} {(u.full_name or ""):<30} {status:<10}')

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
        user = User.query.filter_by(email=email, role='admin').first()

        if not user:
            click.echo(f'No admin with email {email}', err=True)
            raise SystemExit(1)

        password = getpass('New password (min 8 chars): ')
        confirm = getpass('Confirm new password: ')

        if password != confirm:
            click.echo('Passwords do not match.', err=True)
            raise SystemExit(1)
        if len(password) < 8:
            click.echo('Password must be at least 8 characters.', err=True)
            raise SystemExit(1)

        user.set_password(password)
        db.session.commit()
        click.echo(f'Password updated for {user.full_name} <{email}>.')