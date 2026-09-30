"""
scripts/seed_technician.py
Creates technician rows in the real `users` table. Safe to re-run:
if a technician with the same username already exists, it updates the
password instead of raising.

Run from the project root:
    python -m scripts.seed_technician
"""
from app import app, db, User

# Edit this list to match the technicians you want to create.
TECHNICIANS = [
    {
        "username":     "TECH-0001",
        "email":        "carlos.mendoza@devtech.local",
        "full_name":    "Carlos Mendoza",
        "phone":        "09171234567",
        "password":     "TechPass123",
        "id_type":      "National ID",
        "id_number":    "PSN-1234-5678",   # admin-only audit record
        "id_verified":  True,               # so they can be assigned to bookings
    },
    {
        "username":     "TECH-0002",
        "email":        "sarah.lim@devtech.local",
        "full_name":    "Sarah Lim",
        "phone":        "09172345678",
        "password":     "TechPass456",
        "id_type":      "Driver's License",
        "id_number":    "N01-23-456789",
        "id_verified":  True,
    },
]


def upsert(technician):
    existing = User.query.filter_by(username=technician["username"]).first()

    if existing:
        # Ensure role and active are correct even if the row was created
        # manually or by an earlier script version.
        existing.role      = "technician"
        existing.is_active = True
        existing.full_name = technician["full_name"]
        existing.email     = technician["email"]
        existing.phone     = technician.get("phone")
        if technician.get("id_type"):
            existing.id_type   = technician["id_type"]
            existing.id_number = technician["id_number"]
            existing.id_verified    = technician.get("id_verified", False)
            existing.id_verified_at = (
                __import__("datetime").datetime.utcnow()
                if technician.get("id_verified") else None
            )
        existing.set_password(technician["password"])
        action = "updated"
    else:
        u = User(
            username  = technician["username"],
            email     = technician["email"],
            full_name = technician["full_name"],
            phone     = technician.get("phone"),
            role      = "technician",
            is_active = True,
            id_type   = technician.get("id_type"),
            id_number = technician.get("id_number"),
            id_verified = technician.get("id_verified", False),
        )
        u.set_password(technician["password"])
        if technician.get("id_verified"):
            from datetime import datetime
            u.id_verified_at = datetime.utcnow()
        db.session.add(u)
        action = "created"

    db.session.commit()
    print(f"  [{action}] {technician['username']:<10}  "
          f"{technician['full_name']:<20}  password={technician['password']}")


def main():
    with app.app_context():
        print("Seeding technician accounts …")
        for t in TECHNICIANS:
            upsert(t)
        print("Done.")


if __name__ == "__main__":
    main()