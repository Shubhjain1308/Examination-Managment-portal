"""Registers all route groups (blueprints) with the app."""

from .admin import bp as admin_bp
from .auth import bp as auth_bp
from .examiner import bp as examiner_bp
from .student import bp as student_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(examiner_bp)
    app.register_blueprint(student_bp)
