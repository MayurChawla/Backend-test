# Event Booking API

Backend for an **Event Booking System** (hiring exercise): organizers manage events; customers browse and book tickets. Access is enforced by **role-based** JWT authentication. **Background tasks** (FastAPI `BackgroundTasks`) simulate a booking confirmation email and per-customer event update notifications using **stdout / logging** only.

## Initial planning and approach

Before coding, the work was broken into layers so each piece could be reviewed and committed independently:

1. **Runtime and data** — PostgreSQL via Docker Compose for a realistic local environment; SQLAlchemy models aligned with how tickets and ownership would be queried.
2. **Schema evolution** — Alembic from the start so the submission shows migration discipline, not only ORM `create_all`.
3. **Identity and access** — Register/login first, then JWT dependency + role guards so every protected route reuses the same enforcement.
4. **Domain APIs** — Public read for events (browse), organizer write/update, customer booking; ownership checks kept next to event mutations.
5. **Side effects last** — Background tasks only after successful `commit`, using a **new session** inside the task so logging cannot accidentally use a closed request session.

This order matches risk: get auth and schema right, then add business logic and async fire-and-forget behavior.

## Stack

| Choice | Rationale |
|--------|-----------|
| **FastAPI** | Clear dependency injection for RBAC, automatic OpenAPI at `/docs`. |
| **PostgreSQL** | Production-grade ACID database; realistic locking and constraints for ticket inventory. |
| **SQLAlchemy 2.0 (sync)** | Familiar ORM, explicit transactions for booking + inventory updates. |
| **Alembic** | Versioned schema migrations instead of ad-hoc `create_all` in production. |
| **JWT (HS256)** | Stateless auth; role is stored on the user row and re-loaded each request (token `sub` is the source of identity). |
| **FastAPI `BackgroundTasks`** | Meets the assignment’s “job queue or async processing” requirement without running Redis/Celery; tasks run after the response is prepared and use a **new DB session** so they do not leak request-scoped sessions. A README note describes how this could evolve to **Celery + Redis** or **arq**. |
| **Docker Compose** | One-command local Postgres for reviewers and demos. |
| **`pydantic-settings` + `.env`** | Twelve-factor style config; secrets not hardcoded for real deployments. |
| **`python-jose` + `passlib[bcrypt]`** | Widely used, small surface for this scope (vs rolling crypto). |

## Roles and API access

| Role | Allowed operations |
|------|-------------------|
| **organizer** | `POST /events`, `GET /events/me/mine`, `PATCH /events/{id}` (own events only). |
| **customer** | `GET /events/me/bookings`, `POST /events/{id}/bookings`. |
| **Unauthenticated** | `GET /events`, `GET /events/{id}` (public browse). |
| **auth** | `POST /auth/register`, `POST /auth/login` |

Wrong role → **403**. Missing/invalid token on protected routes → **401**.

## Ticket inventory (concurrency)

`events.tickets_remaining` is decremented with a **single conditional `UPDATE`**:

`UPDATE events SET tickets_remaining = tickets_remaining - :q WHERE id = :id AND tickets_remaining >= :q`

If `rowcount != 1`, the API returns **409** and does not insert a booking. This avoids classic read–modify–write races for overselling when combined with a transaction (begin on first query, commit after booking insert).

## Background tasks (assignment)

1. **Booking confirmation** — After a successful commit on `POST /events/{id}/bookings`, a background task logs a line such as:  
   `EMAIL booking_confirmation to=... booking_id=... event_id=...`
2. **Event update** — After `PATCH /events/{id}` by the owner, a background task logs one line per **distinct** booked customer email:  
   `NOTIFY event_updated to=... event_id=...`

If nobody has booked yet, the notifier simply does nothing (no lines).

## Data model decisions

| Topic | Decision | Why |
|-------|----------|-----|
| **Users** | Single `users` table with `role` (`organizer` \| `customer`) | Two actor types without separate tables or duplicate email rows. |
| **Events** | `tickets_total` + `tickets_remaining` on the row | Denormalized counter makes the conditional `UPDATE` for booking one statement; totals stay auditable vs deriving only from `SUM(bookings)`. |
| **Bookings** | One row per booking request with `quantity` | Simple API; multiple rows per customer per event are allowed (no unique constraint) so repeat purchases are possible. |
| **Deletes** | `ON DELETE CASCADE` from users/events to children | Prevents orphan bookings; acceptable for an exercise (production might soft-delete). |
| **Timestamps** | Timezone-aware (`timestamptz`) | Avoids ambiguity for events and logs. |

## API and HTTP semantics

| Topic | Decision | Why |
|-------|----------|-----|
| **Browse** | `GET /events` and `GET /events/{id}` are **public** | Matches “customers browse”; reduces friction for demos and mirrors many ticketing sites. |
| **Organizer “my events”** | `GET /events/me/mine` registered **before** `GET /events/{event_id}` | FastAPI matches in order; otherwise `me` would be parsed as an integer id. |
| **Updates** | `PATCH` (partial) not `PUT` | Organizers can change one field without resending the whole resource. |
| **Non-owner update** | **403 Forbidden** (not 404) | Resource exists but caller is not allowed to act; clearer than pretending the event does not exist. |
| **Missing event on booking** | **404** | Customer targeted a non-existent id. |
| **Oversell / low stock** | **409 Conflict** after failed conditional update | Standard signal that the business invariant (inventory) could not be satisfied. |
| **Booking after end** | **422** if `ends_at` is in the past | Tickets should not be sold for finished events. |
| **Duplicate registration** | **409** on same email | Idempotent UX expectation for “already registered”. |

## Auth decisions

| Topic | Decision | Why |
|-------|----------|-----|
| **Token contents** | JWT `sub` = user id; optional `role` in payload is **not** trusted for authorization | Every protected route loads `User` from DB so role changes and deleted users are respected. |
| **Transport** | Bearer token in `Authorization` header | Stateless, easy in Swagger “Authorize”. |
| **Password API** | `bcrypt` hashes; minimum password length enforced in Pydantic | Reasonable default against trivial passwords without building full password policy UI. |

## Background task decisions

| Topic | Decision | Why |
|-------|----------|-----|
| **Mechanism** | FastAPI `BackgroundTasks` | Satisfies “async processing” for this assignment without operating a second process in CI/review. |
| **When they run** | After successful `db.commit()` in the request path | Matches “triggered when … successfully” in the spec; avoids emailing/logging for rolled-back transactions. |
| **DB in tasks** | Open `SessionLocal()` inside the task, then `close()` | Request session is tied to the request lifecycle; avoids detached instances and connection leaks. |
| **Event update notify** | **Distinct** customer emails | Requirement is to notify all customers who booked; one log line per person avoids spam if they have multiple booking rows. |
| **Output** | `print(..., flush=True)` and `logging` | Visible in `uvicorn` terminal for demos; satisfies “console log / print” wording. |

## Other design choices (summary)

- **No refresh tokens** — Out of scope; documented under future work.
- **No payment / seat map** — Exercise focuses on roles, booking, and notifications.
- **Sync SQLAlchemy** — Fewer moving parts than async engine + session for the same transactional story.
- **Single package layout** (`app/routers`, `app/tasks`) — Keeps the submission small and navigable.

## Run locally

1. Copy `.env.example` to `.env` and adjust if needed (defaults match Docker Compose).
2. Start Postgres:

   ```bash
   docker compose up -d
   ```

3. Create a virtualenv and install dependencies:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Apply migrations:

   ```bash
   alembic upgrade head
   ```

5. Run the API:

   ```bash
   uvicorn app.main:app --reload
   ```

6. Open **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Example flow (Swagger or curl)

1. `POST /auth/register` — organizer (role `organizer`).
2. `POST /auth/login` — copy `access_token`; **Authorize** in Swagger.
3. `POST /events` — create an event with `tickets_total`.
4. Register + login as **customer**; `POST /events/{id}/bookings` with `quantity` — watch the server terminal for **EMAIL** line.
5. Login again as **organizer**; `PATCH /events/{id}` — terminal shows **NOTIFY** lines for each distinct customer.

## Future improvements

- Refresh tokens, OAuth2, and stricter CORS for a browser SPA.
- Idempotency-Key header on bookings to avoid duplicate charges in a payments world.
- Out-of-process workers (Celery/arq) + dead-letter queues for real email/SMS providers.
- Rate limiting and audit log for organizer actions.
