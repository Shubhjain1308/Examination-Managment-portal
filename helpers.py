"""Small helper functions and the business rules used by the routes."""

from datetime import date, datetime

from flask import abort, render_template, url_for
from flask_login import current_user

from config import login_manager

EXAM_TYPES = ["Viva", "Practical", "Project Demo", "Assessment"]
EXAM_STATUSES = ["Draft", "Slot Creation", "Booking Open", "Closed", "Completed"]


# ------------------------------------------------------------------
# Date and time helpers
# ------------------------------------------------------------------
def parse_date(text):
    """'2026-10-15' -> date object (empty text -> None)."""
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def parse_time(text):
    """'10:30' -> time object."""
    return datetime.strptime(text[:5], "%H:%M").time()


def today_is_between(start, end):
    """True if today falls inside the window. A missing date means 'no limit'."""
    today = date.today()

    if start and today < start:
        return False
    if end and today > end:
        return False
    return True


# ------------------------------------------------------------------
# Business rules
# ------------------------------------------------------------------
def can_create_slots(exam):
    """Examiners can create slots only while the exam is in 'Slot Creation' and inside the dates."""
    if exam.status != "Slot Creation":
        return False
    return today_is_between(exam.slot_creation_start, exam.slot_creation_end)


def can_book(exam):
    """Students can book only while the exam is 'Booking Open' and inside the dates."""
    if exam.status != "Booking Open":
        return False
    return today_is_between(exam.booking_start, exam.booking_end)


def can_cancel(exam):
    """Students can cancel only until the booking deadline."""
    if exam.status != "Booking Open":
        return False
    if exam.booking_end and date.today() > exam.booking_end:
        return False
    return True


def booking_has_started(exam):
    """Once booking starts, examiners can no longer edit or remove slots."""
    if exam.status in ("Booking Open", "Closed", "Completed"):
        return True
    if exam.booking_start and date.today() >= exam.booking_start:
        return True
    return False


def active_bookings(slot):
    """Bookings that still use a seat (cancelled ones do not)."""
    return [b for b in slot.bookings if b.status in ("Booked", "Completed")]


def update_slot_seats(slot):
    """Recalculate free seats from the bookings and set the slot status.

    When all seats are taken the slot becomes 'Full' automatically,
    and it becomes 'Available' again if someone cancels.
    """
    if slot.status == "Cancelled":
        return

    used_seats = len(active_bookings(slot))
    slot.available_seats = slot.capacity - used_seats

    if slot.available_seats <= 0:
        slot.status = "Full"
    else:
        slot.status = "Available"


# ------------------------------------------------------------------
# Access control
# ------------------------------------------------------------------
def home_page_for(user):
    """Dashboard URL for each role."""
    pages = {
        "admin": "admin.dashboard",
        "examiner": "examiner.dashboard",
        "student": "student.dashboard",
    }
    return url_for(pages[user.role])


def make_guard(role, approved_only=False):
    """Returns a function that runs before every route of a blueprint.

    It checks that the user is logged in and has the right role.
    For examiners it also checks that the Admin has approved the account.
    """

    def guard():
        if not current_user.is_authenticated:
            return login_manager.unauthorized()

        if current_user.role != role:
            abort(403)

        if approved_only:
            profile = current_user.examiner_profile
            status = profile.status if profile else "Unknown"

            if status != "Approved":
                message = (
                    f"Your examiner account status is: {status}. "
                    "You can use the dashboard after the Admin approves your account."
                )
                return render_template("message.html", kind="warning", msg=message)

    return guard
