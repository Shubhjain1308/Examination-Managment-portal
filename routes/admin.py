"""All Admin pages: courses, exams, rubrics, examiners, slots, bookings and search."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import or_
from werkzeug.security import generate_password_hash

from helpers import EXAM_STATUSES, EXAM_TYPES, make_guard, parse_date, update_slot_seats
from models import (Booking, Course, EvaluationScore, Exam, ExamExaminer,
                    ExaminerProfile, Rubric, Slot, User, db)

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Only logged-in Admins can open any page in this file
bp.before_request(make_guard("admin"))


# ==================================================================
# Dashboard
# ==================================================================
@bp.route("")
def dashboard():
    stats = {
        "Courses": Course.query.count(),
        "Examinations": Exam.query.count(),
        "Examiners": User.query.filter_by(role="examiner").count(),
        "Students": User.query.filter_by(role="student").count(),
        "Slots": Slot.query.count(),
        "Bookings": Booking.query.count(),
    }
    pending_examiners = ExaminerProfile.query.filter_by(status="Pending").count()

    return render_template("dashboard.html", stats=stats, pending=pending_examiners)


# ==================================================================
# Courses  (the same page lists, adds and edits)
# ==================================================================
@bp.route("/courses", methods=["GET", "POST"])
@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def courses(course_id=None):
    course = db.get_or_404(Course, course_id) if course_id else None

    if request.method == "POST":
        form = request.form
        code = form["code"].strip().upper()

        # The course code must be unique
        same_code = Course.query.filter(Course.code == code, Course.id != (course_id or 0)).first()

        if same_code:
            flash("This course code already exists.", "danger")
        else:
            if course is None:
                course = Course()

            course.code = code
            course.name = form["name"].strip()
            course.description = form.get("description")
            course.status = form.get("status", "Active")

            db.session.add(course)
            db.session.commit()
            flash("Course saved.", "success")
            return redirect(url_for("admin.courses"))

    all_courses = Course.query.order_by(Course.id).all()
    return render_template("admin/courses.html", courses=all_courses, course=course)


@bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    course = db.get_or_404(Course, course_id)

    if course.exams:
        flash("This course has exams. Remove them first, or set the course to Inactive.", "danger")
    else:
        db.session.delete(course)
        db.session.commit()
        flash("Course deleted.", "success")

    return redirect(url_for("admin.courses"))


# ==================================================================
# Exams
# ==================================================================
@bp.route("/exams")
def exams():
    all_exams = Exam.query.order_by(Exam.id).all()
    return render_template("admin/exams.html", mode="list", exams=all_exams)


@bp.route("/exams/new", methods=["GET", "POST"])
@bp.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
def exam_form(exam_id=None):
    exam = db.get_or_404(Exam, exam_id) if exam_id else None

    if request.method == "POST":
        form = request.form
        dates = read_exam_dates(form)
        error = check_exam_dates(dates)

        if error:
            flash(error, "danger")
        else:
            if exam is None:
                exam = Exam()

            exam.course_id = int(form["course_id"])
            exam.name = form["name"].strip()
            exam.exam_type = form["exam_type"]
            exam.duration = int(form["duration"])
            exam.max_marks = int(form["max_marks"])
            exam.status = form.get("status", "Draft")

            exam.slot_creation_start = dates["slot_start"]
            exam.slot_creation_end = dates["slot_end"]
            exam.booking_start = dates["booking_start"]
            exam.booking_end = dates["booking_end"]

            db.session.add(exam)
            db.session.commit()
            flash("Exam saved.", "success")
            return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    return render_template(
        "admin/exams.html",
        mode="form",
        exam=exam,
        courses=Course.query.all(),
        types=EXAM_TYPES,
        statuses=EXAM_STATUSES,
    )


def read_exam_dates(form):
    return {
        "slot_start": parse_date(form.get("slot_creation_start")),
        "slot_end": parse_date(form.get("slot_creation_end")),
        "booking_start": parse_date(form.get("booking_start")),
        "booking_end": parse_date(form.get("booking_end")),
    }


def check_exam_dates(dates):
    """Returns an error message, or None if the dates are fine."""
    if dates["slot_start"] and dates["slot_end"] and dates["slot_start"] > dates["slot_end"]:
        return "The slot creation end date cannot be before the start date."

    if dates["booking_start"] and dates["booking_end"] and dates["booking_start"] > dates["booking_end"]:
        return "The booking end date cannot be before the start date."

    return None


@bp.route("/exams/<int:exam_id>")
def exam_detail(exam_id):
    exam = db.get_or_404(Exam, exam_id)

    # Approved examiners who are not yet assigned to this exam
    assigned_ids = [link.examiner_id for link in exam.examiners]
    free_examiners = []
    for user in User.query.filter_by(role="examiner"):
        profile = user.examiner_profile
        if profile and profile.status == "Approved" and user.id not in assigned_ids:
            free_examiners.append(user)

    rubric_total = sum(r.max_marks for r in exam.rubrics)

    return render_template(
        "admin/exam_detail.html",
        exam=exam,
        free_examiners=free_examiners,
        rubric_total=rubric_total,
    )


@bp.route("/exams/<int:exam_id>/delete", methods=["POST"])
def exam_delete(exam_id):
    exam = db.get_or_404(Exam, exam_id)

    if exam.slots:
        flash("This exam already has slots, so it cannot be deleted.", "danger")
        return redirect(url_for("admin.exam_detail", exam_id=exam_id))

    db.session.delete(exam)
    db.session.commit()
    flash("Exam deleted.", "success")
    return redirect(url_for("admin.exams"))


@bp.route("/exams/<int:exam_id>/status", methods=["POST"])
def exam_status(exam_id):
    """Opens or closes slot creation and booking by changing the exam status."""
    exam = db.get_or_404(Exam, exam_id)
    new_status = request.form["status"]

    if new_status in EXAM_STATUSES:
        exam.status = new_status
        db.session.commit()
        flash(f"Exam status changed to: {new_status}", "success")

    return redirect(url_for("admin.exam_detail", exam_id=exam_id))


# ==================================================================
# Rubrics (marking criteria of an exam)
# ==================================================================
@bp.route("/exams/<int:exam_id>/rubrics", methods=["POST"])
def rubric_add(exam_id):
    db.get_or_404(Exam, exam_id)
    form = request.form

    rubric = Rubric(
        exam_id=exam_id,
        criterion_name=form["criterion_name"].strip(),
        max_marks=float(form["max_marks"]),
        weightage=float(form.get("weightage") or 0),
        description=form.get("description"),
    )
    db.session.add(rubric)
    db.session.commit()

    flash("Rubric added.", "success")
    return redirect(url_for("admin.exam_detail", exam_id=exam_id))


@bp.route("/rubrics/<int:rubric_id>/update", methods=["POST"])
def rubric_update(rubric_id):
    rubric = db.get_or_404(Rubric, rubric_id)
    form = request.form

    rubric.criterion_name = form["criterion_name"].strip()
    rubric.max_marks = float(form["max_marks"])
    rubric.weightage = float(form.get("weightage") or 0)
    rubric.description = form.get("description")
    db.session.commit()

    flash("Rubric updated.", "success")
    return redirect(url_for("admin.exam_detail", exam_id=rubric.exam_id))


@bp.route("/rubrics/<int:rubric_id>/delete", methods=["POST"])
def rubric_delete(rubric_id):
    rubric = db.get_or_404(Rubric, rubric_id)
    exam_id = rubric.exam_id

    marks_already_given = EvaluationScore.query.filter_by(rubric_id=rubric_id).first()

    if marks_already_given:
        flash("Marks have already been given for this rubric, so it cannot be deleted.", "danger")
    else:
        db.session.delete(rubric)
        db.session.commit()
        flash("Rubric deleted.", "success")

    return redirect(url_for("admin.exam_detail", exam_id=exam_id))


# ==================================================================
# Assign examiners to an exam
# ==================================================================
@bp.route("/exams/<int:exam_id>/examiners", methods=["POST"])
def exam_assign(exam_id):
    db.get_or_404(Exam, exam_id)
    examiner_id = int(request.form["examiner_id"])

    already_assigned = ExamExaminer.query.filter_by(exam_id=exam_id, examiner_id=examiner_id).first()

    if not already_assigned:
        db.session.add(ExamExaminer(exam_id=exam_id, examiner_id=examiner_id))
        db.session.commit()
        flash("Examiner assigned.", "success")

    return redirect(url_for("admin.exam_detail", exam_id=exam_id))


@bp.route("/exam-examiners/<int:link_id>/delete", methods=["POST"])
def exam_unassign(link_id):
    link = db.get_or_404(ExamExaminer, link_id)
    exam_id = link.exam_id

    has_slots = Slot.query.filter_by(exam_id=exam_id, examiner_id=link.examiner_id).first()

    if has_slots:
        flash("This examiner already has slots. Change the slot examiner first.", "danger")
    else:
        db.session.delete(link)
        db.session.commit()
        flash("Examiner removed from the exam.", "success")

    return redirect(url_for("admin.exam_detail", exam_id=exam_id))


# ==================================================================
# Examiners and students
# ==================================================================
@bp.route("/examiners", methods=["GET", "POST"])
def examiners():
    """Lists examiners. POST adds a new examiner who is approved straight away."""
    if request.method == "POST":
        form = request.form
        email = form["email"].strip().lower()

        if User.query.filter_by(email=email).first():
            flash("This email already exists.", "danger")
        else:
            user = User(
                name=form["name"].strip(),
                email=email,
                password_hash=generate_password_hash(form["password"]),
                role="examiner",
            )
            db.session.add(user)
            db.session.flush()

            profile = ExaminerProfile(user_id=user.id, department=form.get("department"), status="Approved")
            db.session.add(profile)
            db.session.commit()
            flash("Examiner added and approved.", "success")

    all_examiners = User.query.filter_by(role="examiner").all()
    return render_template("admin/users.html", kind="examiner", users=all_examiners)


@bp.route("/examiners/<int:user_id>/<action>", methods=["POST"])
def examiner_action(user_id, action):
    """action is either 'approve' or 'deactivate'."""
    user = db.get_or_404(User, user_id)

    if user.role != "examiner" or action not in ("approve", "deactivate"):
        abort(400)

    if action == "approve":
        user.examiner_profile.status = "Approved"
    else:
        user.examiner_profile.status = "Deactivated"

    db.session.commit()
    flash(f"{user.name} is now {user.examiner_profile.status}.", "success")
    return redirect(url_for("admin.examiners"))


@bp.route("/students")
def students():
    all_students = User.query.filter_by(role="student").all()
    return render_template("admin/users.html", kind="student", users=all_students)


# ==================================================================
# Slots and bookings
# ==================================================================
@bp.route("/slots")
def slots():
    all_slots = Slot.query.order_by(Slot.date, Slot.start_time).all()

    # For each slot: the other examiners of the same exam (to allow changing the examiner)
    other_examiners = {}
    for slot in all_slots:
        other_examiners[slot.id] = [
            link.examiner for link in slot.exam.examiners if link.examiner_id != slot.examiner_id
        ]

    return render_template("admin/schedule.html", view="slots", slots=all_slots, eligible=other_examiners)


@bp.route("/slots/<int:slot_id>/examiner", methods=["POST"])
def slot_change_examiner(slot_id):
    slot = db.get_or_404(Slot, slot_id)
    examiner_id = int(request.form["examiner_id"])

    is_assigned = ExamExaminer.query.filter_by(exam_id=slot.exam_id, examiner_id=examiner_id).first()

    if not is_assigned:
        flash("This examiner is not assigned to this exam.", "danger")
    else:
        slot.examiner_id = examiner_id
        db.session.commit()
        flash("Slot examiner changed.", "success")

    return redirect(url_for("admin.slots"))


def free_slots_for(booking):
    """Other slots of the same exam that still have a free seat."""
    return Slot.query.filter(
        Slot.exam_id == booking.slot.exam_id,
        Slot.id != booking.slot_id,
        Slot.status == "Available",
        Slot.available_seats > 0,
    ).all()


@bp.route("/bookings")
def bookings():
    all_bookings = Booking.query.order_by(Booking.id.desc()).all()

    # For each active booking: the slots it could be moved to
    move_options = {}
    for booking in all_bookings:
        if booking.status == "Booked":
            move_options[booking.id] = free_slots_for(booking)

    return render_template("admin/schedule.html", view="bookings", bookings=all_bookings, options=move_options)


@bp.route("/bookings/<int:booking_id>/reschedule", methods=["POST"])
def booking_reschedule(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    new_slot = db.get_or_404(Slot, int(request.form["slot_id"]))

    if booking.status != "Booked" or new_slot not in free_slots_for(booking):
        flash("Cannot reschedule: the chosen slot is not available.", "danger")
        return redirect(url_for("admin.bookings"))

    old_slot = booking.slot
    booking.slot_id = new_slot.id
    db.session.flush()

    # Reload both slots, then fix their seat counts and status
    db.session.refresh(old_slot)
    db.session.refresh(new_slot)
    update_slot_seats(old_slot)
    update_slot_seats(new_slot)

    db.session.commit()
    flash("Booking rescheduled.", "success")
    return redirect(url_for("admin.bookings"))


# ==================================================================
# Search (name or ID)
# ==================================================================
@bp.route("/search")
def search():
    text = request.args.get("q", "").strip()
    results = {}

    if text:
        like = f"%{text}%"
        number = int(text) if text.isdigit() else -1      # -1 never matches an ID

        results["students"] = User.query.filter(
            User.role == "student",
            or_(User.name.ilike(like), User.email.ilike(like), User.roll_no.ilike(like), User.id == number),
        ).all()

        results["examiners"] = User.query.filter(
            User.role == "examiner",
            or_(User.name.ilike(like), User.email.ilike(like), User.id == number),
        ).all()

        results["exams"] = Exam.query.filter(
            or_(Exam.name.ilike(like), Exam.id == number)
        ).all()

        results["bookings"] = (
            Booking.query.join(User, Booking.student_id == User.id)
            .filter(or_(User.name.ilike(like), Booking.id == number))
            .all()
        )

    return render_template("admin/search.html", q=text, res=results)
