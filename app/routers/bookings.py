from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import Booking, Event, User, UserRole
from app.schemas import BookingCreate, BookingRead
from app.tasks.notifications import send_booking_confirmation_log

router = APIRouter(prefix="/events", tags=["bookings"])


@router.get("/me/bookings", response_model=list[BookingRead])
def list_my_bookings(
    user: User = Depends(require_roles(UserRole.customer)),
    db: Session = Depends(get_db),
) -> list[Booking]:
    """Customer: bookings for the current user (newest first)."""
    stmt = (
        select(Booking)
        .where(Booking.customer_id == user.id)
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("/{event_id}/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    event_id: int,
    body: BookingCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.customer)),
    db: Session = Depends(get_db),
) -> Booking:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if event.ends_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot book tickets for an event that has already ended",
        )

    quantity = body.quantity
    result = db.execute(
        update(Event)
        .where(
            and_(
                Event.id == event_id,
                Event.tickets_remaining >= quantity,
            )
        )
        .values(tickets_remaining=Event.tickets_remaining - quantity)
    )
    if result.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Not enough tickets remaining for this event",
        )

    booking = Booking(customer_id=user.id, event_id=event_id, quantity=quantity)
    db.add(booking)
    db.commit()
    db.refresh(booking)

    background_tasks.add_task(send_booking_confirmation_log, booking.id)
    return booking
