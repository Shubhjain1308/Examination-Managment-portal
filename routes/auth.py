"""Login, logout and registration (students and examiners)."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import home_page_for
from models import ExaminerProfile, User, db

bp = Blueprint("auth", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(home_page_for(current_user))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(home_page_for(user))

        flash("Invalid email or password.", "danger")

    return render_template("auth.html", mode="login")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        form = request.form
        role = form.get("role")
        email = form["email"].strip().lower()

        if role not in ("student", "examiner"):
            abort(400)

        if len(form["password"]) < 6:
            flash("Password must be at least 6 characters.", "danger")

        elif User.query.filter_by(email=email).first():
            flash("This email is already registered.", "danger")

        else:
            create_user(form, role, email)

            message = "Registration successful. Please log in."
            if role == "examiner":
                message += " Your account must be approved by the Admin first."
            flash(message, "success")

            return redirect(url_for("auth.login"))

    return render_template("auth.html", mode="register")


def create_user(form, role, email):
    """Saves a new student or examiner. Examiners start with 'Pending' status."""
    user = User(
        name=form["name"].strip(),
        email=email,
        password_hash=generate_password_hash(form["password"]),
        role=role,
        contact=form.get("contact"),
    )

    if role == "student":
        user.roll_no = form.get("roll_no")

    db.session.add(user)
    db.session.flush()          # gives the new user an id

    if role == "examiner":
        profile = ExaminerProfile(
            user_id=user.id,
            department=form.get("department"),
            status="Pending",
        )
        db.session.add(profile)

    db.session.commit()
