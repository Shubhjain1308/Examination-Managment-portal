"""Settings, login manager and the default Admin account."""

import os

from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from models import db, User

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


# ------------------------------------------------------------------
# 1. Settings
# ------------------------------------------------------------------
class Config:
    # Change this secret key before submitting the project
    SECRET_KEY = "change-this-secret-key"

    # SQLite database file (created automatically on first run)
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "emp.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False


# ------------------------------------------------------------------
# 2. Login manager (Flask-Login)
# ------------------------------------------------------------------
login_manager = LoginManager()

# Where to send users who are not logged in
login_manager.login_view = "auth.login"


# ------------------------------------------------------------------
# 3. Default Admin account (there is no registration page for Admin)
# ------------------------------------------------------------------
def seed_admin():
    # If an admin already exists, do nothing
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
