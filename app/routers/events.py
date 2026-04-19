from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_roles
from app.models import Event, User, UserRole
from app.schemas import EventCreate, EventRead, EventUpdate
from app.tasks.notifications import notify_booked_customers_log

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventRead])
def list_events(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[Event]:
    stmt = select(Event).order_by(Event.starts_at.asc()).offset(skip).limit(limit)
    return list(db.scalars(stmt).all())


@router.get("/me/mine", response_model=list[EventRead])
def list_my_events(
    user: User = Depends(require_roles(UserRole.organizer)),
    db: Session = Depends(get_db),
) -> list[Event]:
    stmt = select(Event).where(Event.organizer_id == user.id).order_by(Event.starts_at.asc())
    return list(db.scalars(stmt).all())


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: Session = Depends(get_db)) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate,
    user: User = Depends(require_roles(UserRole.organizer)),
    db: Session = Depends(get_db),
) -> Event:
    if body.ends_at <= body.starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_at must be after starts_at",
        )
    event = Event(
        organizer_id=user.id,
        title=body.title,
        description=body.description,
        venue=body.venue,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        tickets_total=body.tickets_total,
        tickets_remaining=body.tickets_total,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.patch("/{event_id}", response_model=EventRead)
def update_event(
    event_id: int,
    body: EventUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.organizer)),
    db: Session = Depends(get_db),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.organizer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own events",
        )

    data = body.model_dump(exclude_unset=True)
    if "starts_at" in data or "ends_at" in data:
        starts = data.get("starts_at", event.starts_at)
        ends = data.get("ends_at", event.ends_at)
        if ends <= starts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ends_at must be after starts_at",
            )

    for key, value in data.items():
        setattr(event, key, value)

    db.add(event)
    db.commit()
    db.refresh(event)

    background_tasks.add_task(notify_booked_customers_log, event.id)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    user: User = Depends(require_roles(UserRole.organizer)),
    db: Session = Depends(get_db),
) -> None:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.organizer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own events",
        )
    db.delete(event)
    db.commit()
