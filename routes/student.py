"""Student pages: browse exams, book and cancel slots, see results."""

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from werkzeug.security import generate_password_hash

from helpers import EXAM_TYPES, can_book, can_cancel, make_guard, update_slot_seats
from models import Booking, Course, Exam, Slot, db

bp = Blueprint("student", __name__, url_prefix="/student")

# Only logged-in students can open these pages
bp.before_request(make_guard("student"))


def my_bookings():
    """All bookings of the logged-in student, newest first."""
    return Booking.query.filter_by(student_id=current_user.id).order_by(Booking.id.desc()).all()


def has_booked_exam(exam_id):
    """True if the student already has a booking (not cancelled) for this exam."""
    booking = (
        Booking.query.join(Slot)
        .filter(
            Booking.student_id == current_user.id,
            Slot.exam_id == exam_id,
            Booking.status.in_(["Booked", "Completed"]),
        )
        .first()
    )
    return booking


# ==================================================================
# Dashboard
# ==================================================================
@bp.route("")
def dashboard():
    open_exams = Exam.query.filter_by(status="Booking Open").all()

    available_slots = []
    for exam in open_exams:
        for slot in exam.slots:
            if slot.status == "Available":
                available_slots.append(slot)

    bookings = my_bookings()

    upcoming = [b for b in bookings if b.status == "Booked" and b.slot.date >= date.today()]
    published_results = [b for b in bookings if b.evaluation and b.evaluation.is_published]

    return render_template(
        "dashboard.html",
        open_exams=open_exams,
        slots=available_slots,
        upcoming=upcoming,
        results=published_results,
    )


# ==================================================================
# Browse exams (search and filter)
# ==================================================================
@bp.route("/exams")
def exams():
    text = request.args.get("q", "").strip()
    exam_type = request.args.get("type", "")

    query = Exam.query.join(Course).filter(Exam.status != "Draft")

    if text:
        like = f"%{text}%"
        query = query.filter(or_(Exam.name.ilike(like), Course.name.ilike(like), Course.code.ilike(like)))

    if exam_type:
        query = query.filter(Exam.exam_type == exam_type)

    return render_template(
        "student/exams.html",
        mode="list",
        exams=query.all(),
        q=text,
        t=exam_type,
        types=EXAM_TYPES,
    )


@bp.route("/exams/<int:exam_id>")
def exam_view(exam_id):
    exam = db.get_or_404(Exam, exam_id)

    return render_template(
        "student/exams.html",
        mode="detail",
        exam=exam,
        my_booking=has_booked_exam(exam_id),
        can_book=can_book(exam),
    )


# ==================================================================
# Book and cancel
# ==================================================================
def get_booking_error(slot):
    """Returns the reason why booking is not allowed, or None if it is allowed."""
    exam = slot.exam

    if not can_book(exam):
        return "Booking is not open for this exam."

    if has_booked_exam(exam.id):
        return "You have already booked a slot for this exam."

    if slot.status != "Available" or slot.available_seats <= 0:
        return "This slot is full."

    return None


@bp.route("/book/<int:slot_id>", methods=["POST"])
def book_slot(slot_id):
    slot = db.get_or_404(Slot, slot_id)

    error = get_booking_error(slot)
    if error:
        flash(error, "danger")
        return redirect(url_for("student.exam_view", exam_id=slot.exam_id))

    booking = Booking(student_id=current_user.id, slot_id=slot.id, status="Booked")
    db.session.add(booking)
    db.session.flush()

    # Reduce the free seats (the slot becomes 'Full' when the last seat is taken)
    db.session.refresh(slot)
    update_slot_seats(slot)

    db.session.commit()
    flash("Slot booked successfully.", "success")
    return redirect(url_for("student.bookings"))


@bp.route("/cancel/<int:booking_id>", methods=["POST"])
def cancel_booking(booking_id):
    booking = db.get_or_404(Booking, booking_id)

    if booking.student_id != current_user.id:
        abort(403)

    if booking.status != "Booked" or not can_cancel(booking.slot.exam):
        flash("This booking cannot be cancelled (the deadline has passed).", "danger")
        return redirect(url_for("student.bookings"))

    booking.status = "Cancelled"
    db.session.flush()

    # Give the seat back (the slot becomes 'Available' again)
    db.session.refresh(booking.slot)
    update_slot_seats(booking.slot)

    db.session.commit()
    flash("Booking cancelled.", "success")
    return redirect(url_for("student.bookings"))


# ==================================================================
# Booking history and results
# ==================================================================
@bp.route("/bookings")
def bookings():
    return render_template(
        "student/bookings.html",
        mode="history",
        bookings=my_bookings(),
        can_cancel=can_cancel,
    )


@bp.route("/results")
def results():
    published = [b for b in my_bookings() if b.evaluation and b.evaluation.is_published]
    return render_template("student/bookings.html", mode="results", bookings=published)


# ==================================================================
# Profile
# ==================================================================
@bp.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        form = request.form
        new_password = form.get("password")

        if new_password and len(new_password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            current_user.name = form["name"].strip()
            current_user.contact = form.get("contact")
            current_user.roll_no = form.get("roll_no")

            if new_password:
                current_user.password_hash = generate_password_hash(new_password)

            db.session.commit()
            flash("Profile updated.", "success")

    return render_template("student/profile.html")
