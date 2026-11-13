"""Database tables.

Main chain:  Course -> Exam -> Slot -> Booking -> Evaluation -> EvaluationScore
"""

from datetime import datetime, date

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Admin, Examiner and Student all live in this table (the 'role' column tells them apart)."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)      # admin / examiner / student
    contact = db.Column(db.String(20))
    roll_no = db.Column(db.String(30))                   # used by students only
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    examiner_profile = db.relationship(
        "ExaminerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    bookings = db.relationship("Booking", back_populates="student")
    slots = db.relationship("Slot", back_populates="examiner")


class ExaminerProfile(db.Model):
    """Extra details for examiners, including the approval status."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    department = db.Column(db.String(100))
    status = db.Column(db.String(20), default="Pending")  # Pending / Approved / Deactivated

    user = db.relationship("User", back_populates="examiner_profile")


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="Active")   # Active / Inactive

    exams = db.relationship("Exam", back_populates="course")


class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(db.String(30), nullable=False)  # Viva / Practical / Project Demo / Assessment
    duration = db.Column(db.Integer, nullable=False)      # in minutes
    max_marks = db.Column(db.Integer, nullable=False)

    # The two time windows set by the Admin
    slot_creation_start = db.Column(db.Date)
    slot_creation_end = db.Column(db.Date)
    booking_start = db.Column(db.Date)
    booking_end = db.Column(db.Date)

    # Draft / Slot Creation / Booking Open / Closed / Completed
    status = db.Column(db.String(20), default="Draft")

    course = db.relationship("Course", back_populates="exams")
    rubrics = db.relationship("Rubric", back_populates="exam", cascade="all, delete-orphan")
    slots = db.relationship("Slot", back_populates="exam")
    examiners = db.relationship("ExamExaminer", back_populates="exam", cascade="all, delete-orphan")


class ExamExaminer(db.Model):
    """Links an exam to the examiners assigned to it (many-to-many)."""

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    exam = db.relationship("Exam", back_populates="examiners")
    examiner = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("exam_id", "examiner_id"),)


class Rubric(db.Model):
    """One marking criterion of an exam, e.g. 'Coding - 15 marks'."""

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    criterion_name = db.Column(db.String(100), nullable=False)
    max_marks = db.Column(db.Float, nullable=False)
    weightage = db.Column(db.Float, default=0)
    description = db.Column(db.Text)

    exam = db.relationship("Exam", back_populates="rubrics")


class Slot(db.Model):
    """A time slot created by an examiner. Students book seats in it."""

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exam.id"), nullable=False)
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    available_seats = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="Available")  # Available / Full / Cancelled / Completed

    exam = db.relationship("Exam", back_populates="slots")
    examiner = db.relationship("User", back_populates="slots")
    bookings = db.relationship("Booking", back_populates="slot")


class Booking(db.Model):
    """A student's seat in a slot."""

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey("slot.id"), nullable=False)
    booking_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(20), default="Booked")     # Booked / Cancelled / Completed

    student = db.relationship("User", back_populates="bookings")
    slot = db.relationship("Slot", back_populates="bookings")
    evaluation = db.relationship("Evaluation", back_populates="booking", uselist=False)


class Evaluation(db.Model):
    """The examiner's result for one booking."""

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), unique=True, nullable=False)
    total_marks = db.Column(db.Float, default=0)
    remarks = db.Column(db.Text)
    is_published = db.Column(db.Boolean, default=False)     # students see it only when True
    evaluated_at = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship("Booking", back_populates="evaluation")
    scores = db.relationship("EvaluationScore", back_populates="evaluation", cascade="all, delete-orphan")


class EvaluationScore(db.Model):
    """Marks given for one rubric criterion inside an evaluation."""

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.Integer, db.ForeignKey("evaluation.id"), nullable=False)
    rubric_id = db.Column(db.Integer, db.ForeignKey("rubric.id"), nullable=False)
    marks_awarded = db.Column(db.Float, nullable=False)

    evaluation = db.relationship("Evaluation", back_populates="scores")
    rubric = db.relationship("Rubric")
