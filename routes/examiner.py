"""Examiner pages: create slots, see booked students, give marks."""

from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from helpers import (active_bookings, booking_has_started, can_create_slots,
                     make_guard, parse_date, parse_time)
from models import (Booking, Evaluation, EvaluationScore, Exam, ExamExaminer,
                    Slot, db)

bp = Blueprint("examiner", __name__, url_prefix="/examiner")

# Only logged-in examiners approved by the Admin can open these pages
bp.before_request(make_guard("examiner", approved_only=True))


# ==================================================================
# Dashboard
# ==================================================================
@bp.route("")
def dashboard():
    my_slots = Slot.query.filter_by(examiner_id=current_user.id).order_by(Slot.date).all()

    assigned_exams = [link.exam for link in ExamExaminer.query.filter_by(examiner_id=current_user.id)]

    students_booked = sum(len(active_bookings(slot)) for slot in my_slots)

    # Bookings that are not evaluated yet
    pending = []
    for slot in my_slots:
        for booking in slot.bookings:
            if booking.status == "Booked" and not booking.evaluation:
                pending.append(booking)

    return render_template(
        "dashboard.html",
        exams=assigned_exams,
        slots=my_slots,
        booked=students_booked,
        pending=pending,
    )


# ==================================================================
# Create, edit and delete slots
# ==================================================================
def get_slot_error(exam, slot_date, start, end, capacity):
    """Returns an error message, or None if the slot details are valid."""
    if not can_create_slots(exam):
        return "The slot creation period is not open for this exam right now."
    if start >= end:
        return "The end time must be after the start time."
    if capacity < 1:
        return "Capacity must be at least 1."
    return None


@bp.route("/slots/new", methods=["GET", "POST"])
@bp.route("/slots/<int:slot_id>/edit", methods=["GET", "POST"])
def slot_form(slot_id=None):
    slot = db.get_or_404(Slot, slot_id) if slot_id else None

    # When editing: it must be my slot, and booking must not have started
    if slot:
        if slot.examiner_id != current_user.id:
            abort(403)
        if booking_has_started(slot.exam) or active_bookings(slot):
            flash("This slot cannot be edited after booking has started.", "danger")
            return redirect(url_for("examiner.dashboard"))

    # Only exams whose slot creation period is open can be chosen
    open_exams = []
    for link in ExamExaminer.query.filter_by(examiner_id=current_user.id):
        if can_create_slots(link.exam):
            open_exams.append(link.exam)

    if request.method == "POST":
        form = request.form
        exam = db.get_or_404(Exam, int(form["exam_id"]))

        # The examiner must be assigned to this exam
        assigned = ExamExaminer.query.filter_by(exam_id=exam.id, examiner_id=current_user.id).first()
        if not assigned:
            abort(403)

        slot_date = parse_date(form["date"])
        start = parse_time(form["start_time"])
        end = parse_time(form["end_time"])
        capacity = int(form["capacity"])

        error = get_slot_error(exam, slot_date, start, end, capacity)

        if error:
            flash(error, "danger")
        else:
            if slot is None:
                slot = Slot(examiner_id=current_user.id)

            slot.exam_id = exam.id
            slot.date = slot_date
            slot.start_time = start
            slot.end_time = end
            slot.capacity = capacity
            slot.available_seats = capacity
            slot.status = "Available"

            db.session.add(slot)
            db.session.commit()
            flash("Slot saved.", "success")
            return redirect(url_for("examiner.dashboard"))

    return render_template("examiner/slot_form.html", slot=slot, exams=open_exams)


@bp.route("/slots/<int:slot_id>/delete", methods=["POST"])
def slot_delete(slot_id):
    slot = db.get_or_404(Slot, slot_id)

    if slot.examiner_id != current_user.id:
        abort(403)

    if booking_has_started(slot.exam) or active_bookings(slot):
        flash("This slot cannot be removed after booking has started.", "danger")
        return redirect(url_for("examiner.dashboard"))

    for booking in list(slot.bookings):
        db.session.delete(booking)
    db.session.delete(slot)
    db.session.commit()

    flash("Slot removed.", "success")
    return redirect(url_for("examiner.dashboard"))


# ==================================================================
# Booked students and evaluation
# ==================================================================
@bp.route("/slots/<int:slot_id>")
def slot_detail(slot_id):
    """Shows the booked students.

    If the URL has ?evaluate=<booking_id>, the marks form is shown below the table.
    """
    slot = db.get_or_404(Slot, slot_id)

    if slot.examiner_id != current_user.id:
        abort(403)

    booking_to_evaluate = None
    old_scores = {}

    booking_id = request.args.get("evaluate", type=int)

    if booking_id:
        booking_to_evaluate = find_booking(slot, booking_id)

        if not slot.exam.rubrics:
            flash("The Admin has not created rubrics for this exam yet.", "danger")
            return redirect(url_for("examiner.slot_detail", slot_id=slot_id))

        # Marks given earlier (used to pre-fill the form when re-evaluating)
        if booking_to_evaluate.evaluation:
            for score in booking_to_evaluate.evaluation.scores:
                old_scores[score.rubric_id] = score.marks_awarded

    return render_template(
        "examiner/slot_detail.html",
        slot=slot,
        eb=booking_to_evaluate,
        existing=old_scores,
    )


def find_booking(slot, booking_id):
    """Finds a non-cancelled booking inside this slot, or shows a 404 page."""
    for booking in slot.bookings:
        if booking.id == booking_id and booking.status != "Cancelled":
            return booking
    abort(404)


def read_scores(rubrics, form):
    """Reads and checks the marks from the form.

    Returns (scores, ok).  scores is a dict {rubric_id: marks}.
    """
    scores = {}
    ok = True

    for rubric in rubrics:
        try:
            marks = float(form[f"score_{rubric.id}"])
        except (KeyError, ValueError):
            marks = -1

        if marks < 0 or marks > rubric.max_marks:
            flash(f"Marks for '{rubric.criterion_name}' must be between 0 and {rubric.max_marks:g}.", "danger")
            ok = False

        scores[rubric.id] = marks

    return scores, ok


@bp.route("/evaluate/<int:booking_id>", methods=["POST"])
def evaluate(booking_id):
    booking = db.get_or_404(Booking, booking_id)

    # An examiner can only evaluate students of his or her own slots
    if booking.slot.examiner_id != current_user.id:
        abort(403)

    slot_page = url_for("examiner.slot_detail", slot_id=booking.slot_id)
    form_page = url_for("examiner.slot_detail", slot_id=booking.slot_id, evaluate=booking.id)

    if booking.status == "Cancelled" or not booking.slot.exam.rubrics:
        flash("This booking cannot be evaluated.", "danger")
        return redirect(slot_page)

    scores, ok = read_scores(booking.slot.exam.rubrics, request.form)
    if not ok:
        return redirect(form_page)

    # Create the evaluation, or reuse the old one when re-evaluating
    evaluation = booking.evaluation or Evaluation(booking_id=booking.id)
    db.session.add(evaluation)
    evaluation.scores.clear()
    db.session.flush()

    for rubric_id, marks in scores.items():
        evaluation.scores.append(EvaluationScore(rubric_id=rubric_id, marks_awarded=marks))

    evaluation.total_marks = sum(scores.values())
    evaluation.remarks = request.form.get("remarks")
    evaluation.is_published = "publish" in request.form
    evaluation.evaluated_at = datetime.utcnow()

    booking.status = "Completed"
    db.session.commit()

    flash("Evaluation saved.", "success")
    return redirect(slot_page)
