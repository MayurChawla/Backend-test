import logging

from fastapi import FastAPI

from app.routers import auth, bookings, events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Event Booking API", version="0.1.0")

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(bookings.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
