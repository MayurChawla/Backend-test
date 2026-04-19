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
| **`python-jose` + `bcrypt`** | Direct `bcrypt` hashing avoids **passlib** incompatibility with **bcrypt 4.1+** (`__about__` removed, stricter 72-byte checks during passlib init). |

## Roles and API access

| Role | Allowed operations |
|------|-------------------|
| **organizer** | `POST /events`, `GET /events/me/mine`, `PATCH /events/{id}`, `DELETE /events/{id}` (own events only). |
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

### Where this lives in code

| Assignment item | Trigger | Implementation |
|-----------------|---------|------------------|
| Background Task 1 (booking email) | Successful booking commit | [`app/routers/bookings.py`](app/routers/bookings.py) → `BackgroundTasks.add_task(send_booking_confirmation_log, …)` → [`app/tasks/notifications.py`](app/tasks/notifications.py) |
| Background Task 2 (event updated) | Successful PATCH with at least one field | [`app/routers/events.py`](app/routers/events.py) → `BackgroundTasks.add_task(notify_booked_customers_log, …)` → [`app/tasks/notifications.py`](app/tasks/notifications.py) |

An empty `PATCH` body (no fields to change) returns the current event and **does not** enqueue Task 2, since nothing was persisted.

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
| **Password API** | `bcrypt` (library) hashes; passwords over 72 **bytes** are truncated before hashing (bcrypt limit); min length enforced in Pydantic | Same security family as passlib-bcrypt without the broken version pairing on modern installs. |

## Background task decisions

| Topic | Decision | Why |
|-------|----------|-----|
| **Mechanism** | FastAPI `BackgroundTasks` | Satisfies “async processing” for this assignment without operating a second process in CI/review. |
| **When they run** | After successful `db.commit()` in the request path | Matches “triggered when … successfully” in the spec; avoids emailing/logging for rolled-back transactions. |
| **DB in tasks** | Open `SessionLocal()` inside the task, then `close()` | Request session is tied to the request lifecycle; avoids detached instances and connection leaks. |
| **Event update notify** | **Distinct** customer emails | Requirement is to notify all customers who booked; one log line per person avoids spam if they have multiple booking rows. |
| **Notify only on real updates** | Task 2 runs only when `PATCH` included at least one field | Avoids spurious “event updated” logs for no-op requests. |
| **Output** | `print(..., flush=True)` and `logging` | Visible in `uvicorn` terminal for demos; satisfies “console log / print” wording. |
| **Process logging** | `logging.basicConfig` in [`app/main.py`](app/main.py) | Ensures `logging.info` lines from task helpers show up during `uvicorn` runs without extra config. |

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

## API reference (all routes)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Liveness probe |
| POST | `/auth/register` | No | Create user (`organizer` or `customer`) |
| POST | `/auth/login` | No | JWT access token |
| GET | `/events` | No | List events (paginated) |
| GET | `/events/me/mine` | Organizer | List my events |
| GET | `/events/{event_id}` | No | Event detail |
| POST | `/events` | Organizer | Create event |
| PATCH | `/events/{event_id}` | Organizer | Update own event (triggers Task 2 when body has fields) |
| DELETE | `/events/{event_id}` | Organizer | Delete own event |
| GET | `/events/me/bookings` | Customer | List my bookings |
| POST | `/events/{event_id}/bookings` | Customer | Book tickets (triggers Task 1) |

## Example flow (Swagger or curl)

1. `POST /auth/register` — organizer (role `organizer`).
2. `POST /auth/login` — copy `access_token`; **Authorize** in Swagger.
3. `POST /events` — create an event with `tickets_total`.
4. Register + login as **customer**; `POST /events/{id}/bookings` with `quantity` — watch the server terminal for **EMAIL** line.
5. Login again as **organizer**; `PATCH /events/{id}` — terminal shows **NOTIFY** lines for each distinct customer.
6. (Optional) As customer, `GET /events/me/bookings` to list purchases.

## Demo video (assignment deliverable)

The brief asks for a **screen recording** (e.g. [Loom](https://www.loom.com/) or similar) that demonstrates what you built, with these constraints:

- **Length:** at least **2 minutes**, at most **5 minutes** (about **3–4 minutes** is ideal).
- **Face on camera** — required.
- **English** narration while you walk through the demo.

Suggested talking points:

1. Show **Swagger** (`/docs`): register organizer and customer, login, authorize.
2. Organizer: **create** an event; customer: **browse** and **book**; point at the terminal for the **EMAIL** log line.
3. Organizer: **PATCH** the event; point at **NOTIFY** log lines for booked customers.
4. In one sentence, mention **Postgres + Alembic** and **role-based** access.

This repository does not include the video file; upload it per the employer’s instructions.

## Submission checklist (maps to the brief)

- [ ] **Two user types** — organizers manage events; customers browse and book (`UserRole`, route guards).
- [ ] **Role-based API access** — wrong role → 403; protected routes require Bearer JWT.
- [ ] **Background Task 1** — booking confirmation simulated with **print/log** after successful booking.
- [ ] **Background Task 2** — event update notifies **distinct** booked customers via **print/log** after a successful PATCH with changes.
- [ ] **Design decisions** — documented in this README (stack, model, HTTP semantics, tasks).
- [ ] **Demo video** — recorded per section above (face + English + 2–5 min).

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `could not connect to server` (Alembic or app) | Run `docker compose up -d` and wait until Postgres is healthy (`docker compose ps`). |
| Port **5432** already in use | Stop the other Postgres instance, or change the host port in `docker-compose.yml` and set `DATABASE_URL` in `.env` to match. |
| `alembic` not found | Use the same environment as the app: `.\.venv\Scripts\alembic upgrade head` (Windows) or `venv/bin/alembic upgrade head` (Unix). |
| No **EMAIL** / **NOTIFY** lines in the terminal | Background tasks run **after** the response; keep the server terminal visible. Ensure `PATCH` included at least one field (empty body skips Task 2). |
| `passlib` / `bcrypt.__about__` / 72-byte errors on register | This repo uses the **`bcrypt`** package directly (see `app/security.py`). Reinstall deps: `pip install -r requirements.txt` and remove old `passlib` if you no longer need it. |

## AI tools

The assignment allows using **AI tools** (e.g. assistants, codegen). This project was developed with that in mind: generated or suggested code was still **reviewed** for security (auth, SQL injection via ORM), correctness (ticket concurrency), and fit to the brief.

## Future improvements

- Refresh tokens, OAuth2, and stricter CORS for a browser SPA.
- Idempotency-Key header on bookings to avoid duplicate charges in a payments world.
- Out-of-process workers (Celery/arq) + dead-letter queues for real email/SMS providers.
- Rate limiting and audit log for organizer actions.
