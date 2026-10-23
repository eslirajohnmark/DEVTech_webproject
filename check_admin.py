"""Report whether any admin account exists. Read-only: never creates one.

To create an admin, run:  flask --app app create-admin
"""
from app import app, Admin


def check_admin():
    with app.app_context():
        admins = Admin.query.order_by(Admin.created_at).all()
        if not admins:
            print("No admin account exists.")
            print("Create one with:  flask --app app create-admin")
            return
        for a in admins:
            status = 'active' if a.is_active else 'INACTIVE'
            print(f"Admin: {a.email} ({status})")


if __name__ == '__main__':
    check_admin()
