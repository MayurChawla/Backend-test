import logging
from collections.abc import Sequence

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Booking, Event, User

logger = logging.getLogger(__name__)


def send_booking_confirmation_log(booking_id: int) -> None:
    """Simulated async email after a successful booking (assignment: log only)."""
    db = SessionLocal()
    try:
        booking = db.get(Booking, booking_id)
        if booking is None:
            logger.warning("booking_confirmation: booking %s not found", booking_id)
            return
        customer = db.get(User, booking.customer_id)
        event = db.get(Event, booking.event_id)
        email = customer.email if customer else "unknown"
        title = event.title if event else "unknown"
        msg = (
            f"EMAIL booking_confirmation to={email} "
            f"booking_id={booking_id} event_id={booking.event_id} "
            f"event_title={title!r} quantity={booking.quantity}"
        )
        logger.info(msg)
        print(msg, flush=True)
    finally:
        db.close()


def notify_booked_customers_log(event_id: int) -> None:
    """Simulated notify-all-customers after an event update (assignment: log only)."""
    db = SessionLocal()
    try:
        emails: Sequence[str] = (
            db.execute(
                select(User.email)
                .join(Booking, Booking.customer_id == User.id)
                .where(Booking.event_id == event_id)
                .distinct()
            )
            .scalars()
            .all()
        )
        for email in emails:
            msg = f"NOTIFY event_updated to={email} event_id={event_id}"
            logger.info(msg)
            print(msg, flush=True)
    finally:
        db.close()
