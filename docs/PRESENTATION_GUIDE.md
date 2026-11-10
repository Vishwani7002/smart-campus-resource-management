# 🎤 Presentation & Viva Preparation Guide

## A. 60-second pitch (memorise this)
> "Campus rooms, labs and equipment are usually booked on paper or WhatsApp, which causes double-bookings and wasted resources. Our system stores every resource, booking and maintenance window in a relational database and lets the **database itself** reject conflicting bookings using triggers, constraints and transactions. On top of that we built a REST backend, a responsive web interface and a command-line client, with approval workflow, notifications, audit logs and utilisation reports."

## B. Slide outline (10–12 slides, ~10 minutes)
| # | Slide | What to say / show |
|---|---|---|
| 1 | Title | Project name, your name, guide, date |
| 2 | Problem | Manual booking → clashes, idle rooms, no history, maintenance surprises |
| 3 | Objectives | Allocate, prevent conflicts, track maintenance, report usage, multi-user roles |
| 4 | Architecture | Browser / CLI → Flask API → service layer → SQLite (draw the 4 boxes) |
| 5 | ER diagram | Use `docs/ER_Diagram.png`; point to the self-referencing FK |
| 6 | Schema & normalisation | 8 tables, 3NF, lookup tables, constraints list |
| 7 | **Conflict detection (hero slide)** | Overlap formula, BEFORE INSERT trigger code, why DB-level is safer than app-level |
| 8 | Transactions & concurrency | ACID, `BEGIN IMMEDIATE`, 10-thread test: 1 wins, 9 blocked |
| 9 | Other DBMS features | Views, indexes, triggers (cascade, audit, notify), joins, subqueries, HAVING |
| 10 | Live demo | See script below |
| 11 | Results & testing | 8 automated tests, 100+ seeded bookings, reports |
| 12 | Future scope & conclusion | PostgreSQL/MySQL, email/SMS alerts, QR check-in, recurring bookings, timetable import, AI suggestions |

## C. Live demo script (5 minutes — rehearse twice)
1. **Open the web app** → *Create account* → register as a new student (shows "take new user information"). You land on the dashboard.
2. **Book a resource**: tomorrow 14:00–15:00 → choose *Classroom A-101* → title → *Confirm*. Toast says "pending approval".
3. **Create the conflict**: book *Classroom A-101* again for 14:30–15:30. Red panel appears: *"Resource is already booked…"* with **free time slots** and **other free classrooms**. Say: *"This message came from the database trigger, not from front-end code."* Click a suggested slot → booked.
4. **Log out → log in as admin** (demo button). Show **dashboard counter "double-bookings blocked"**, open **All bookings** → **Approve** the student's request. Log in again as the student → 🔔 shows the notification.
5. **Maintenance cascade**: as admin → *Maintenance → Schedule* on the room you booked, covering the booking. Toast: "1 clashing booking cancelled". Explain the trigger.
6. **Schedule** page → show the timeline (booked, pending, maintenance blocks).
7. **Reports** → utilisation, peak hours; **Audit log** → every action recorded by triggers.
8. **CLI**: open a terminal → `python cli.py` → login → *Find available resources* → *Book* the same slot → show the same conflict message. Say: *"Same service layer, same database."*
9. **Raw SQL proof** (impress the examiner): `python docs/run_demo_queries.py` – the overlapping INSERT is rejected even without our app.
10. `python tests.py` – show 8 passing tests including the concurrency test.

## D. Code you should be able to explain line-by-line
`schema.sql` → `trg_booking_before_insert` (the 4 checks) · `db.py` → `transaction()` · `services.py` → `create_booking()` and `free_slots()` · the `availability` SQL with `NOT EXISTS`.

## E. Likely viva questions & model answers
1. **Why a trigger instead of checking in the app?** The database is the single point every client passes through. App-level checks can be bypassed by bugs, other apps or race conditions; a trigger inside the transaction guarantees integrity.
2. **How do you detect overlap?** Two intervals overlap iff `A.start < B.end AND A.end > B.start`. Back-to-back bookings (10–11 and 11–12) are allowed.
3. **What if two users book at the same millisecond?** `BEGIN IMMEDIATE` acquires SQLite's write lock first, so transactions are serialised; the second insert sees the first and the trigger rejects it. Proven in `tests.py` (10 threads → 1 success).
4. **Explain ACID.** Atomicity – insert + triggers + audit commit together or roll back. Consistency – constraints/triggers keep rules true. Isolation – write lock. Durability – committed data persists in the DB file.
5. **Which normal form? Why?** 3NF; departments and resource_types are separated so names aren't repeated; no transitive dependencies.
6. **What is a self-referencing foreign key?** `resources.parent_id → resources.resource_id`; models equipment inside a room.
7. **Why an index on (resource_id, start_time, end_time)?** Overlap checks always filter by resource then time range; the composite index avoids full table scans.
8. **What is a view and why use it?** A stored query. `v_booking_details` hides a 4-table join; `v_resource_utilization` encapsulates aggregation.
9. **How is security handled?** PBKDF2-SHA256 with random salt per user, parameterised queries (no SQL injection), role checks on every admin API, session cookies, HTML escaping.
10. **Difference between CHECK, UNIQUE, FOREIGN KEY, trigger?** Column/row rules vs uniqueness vs referential integrity vs procedural rules across rows/tables.
11. **What happens when maintenance is scheduled over bookings?** An AFTER INSERT trigger cancels them, writes the audit log; another trigger notifies the users.
12. **Why SQLite? Can it scale?** Zero-config, ACID, perfect for demo. Only `db.py` and a few SQL functions (`julianday`, `strftime`) would change for PostgreSQL/MySQL; the schema/triggers port easily.
13. **Why do pending bookings block the slot?** To avoid two people both "winning" until approval; the admin approves, nothing can clash.
14. **How do you prevent bookings in the past or outside hours?** Validation in the service layer (rules that depend on the current time can't be expressed as static CHECKs) plus CHECK constraints for static rules.
15. **What is the difference between DELETE and retiring a resource?** FK `ON DELETE RESTRICT` protects history; we retire (status = retired) to keep reports accurate.
16. **How does the CLI share logic with the website?** Both call `services.py`; no duplicated rules.
17. **What are views vs. materialised views?** Views are virtual (recomputed each time); SQLite has none materialised – we could cache in a table.
18. **What does `PRAGMA foreign_keys = ON` do?** SQLite ignores FKs by default; this enforces them per connection.
19. **How did you test?** `tests.py` (unit + trigger + concurrency), manual UI tests, 100+ generated bookings in `seed.py` where clashes were automatically rejected.
20. **Future scope?** Email/SMS, recurring bookings, QR check-in, timetable import, role hierarchy, Postgres, Docker, analytics ML for demand forecasting.

## F. Last-minute checklist
- [ ] `pip install -r requirements.txt` works on the presentation laptop
- [ ] `python cli.py seed` – fresh data on the day (stop web server first)
- [ ] Browser zoom 100–110 %, window maximised, second terminal open for the CLI demo
- [ ] Printed copy of `ER_Diagram.png`
- [ ] Know the 4 demo logins (see README)
- [ ] Have a backup: screenshots of each page in case the laptop fails
