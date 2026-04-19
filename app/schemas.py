from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    venue: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime
    tickets_total: int = Field(ge=1)


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    venue: str | None = Field(default=None, min_length=1, max_length=500)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organizer_id: int
    title: str
    description: str
    venue: str
    starts_at: datetime
    ends_at: datetime
    tickets_total: int
    tickets_remaining: int
    created_at: datetime
    updated_at: datetime


class BookingCreate(BaseModel):
    quantity: int = Field(ge=1)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    customer_id: int
    quantity: int
    created_at: datetime
