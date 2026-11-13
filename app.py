"""Application entry point.  Run with:  python app.py"""

from flask import Flask, render_template

from config import Config, login_manager, seed_admin
from models import db, User
from routes import register_blueprints


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Connect the extensions and the routes to the app
    db.init_app(app)
    login_manager.init_app(app)
    register_blueprints(app)

    # Flask-Login uses this to find the logged-in user in the database
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Shown when a user opens a page that is not allowed for their role
    @app.errorhandler(403)
    def access_denied(error):
        return render_template("message.html", kind="danger", msg="Access denied (403)"), 403

    # Create all tables and the Admin account from code
    with app.app_context():
        db.create_all()
        seed_admin()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
