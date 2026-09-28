from app import app, db, User

def check_and_create_admin():
    with app.app_context():
        admin = User.query.filter_by(email='admin@devtech.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@devtech.com',
                full_name='System Administrator',
                phone='09171234567',
                role='admin',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin user created successfully!")
            print("   Email: admin@devtech.com")
            print("   Password: admin123")
        else:
            print("✅ Admin user already exists.")
            print(f"   Email: {admin.email}")
            print("   Password: admin123 (if not changed)")

if __name__ == '__main__':
    check_and_create_admin()