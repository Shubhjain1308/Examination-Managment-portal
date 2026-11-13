from werkzeug.security import generate_password_hash
from models import db, User


def seed_admin():
    admin_exists = User.query.filter_by(role="admin").first()

    if admin_exists:
        return

    admin = User(
        name="Admin",
        email="admin@emp.com",
        password_hash=generate_password_hash("admin123"),
        role="admin",
    )
    db.session.add(admin)
    db.session.commit()
