#!/usr/bin/env python3
"""
Smart Campus - Command Line Interface
-------------------------------------
  python cli.py             interactive terminal app (login / register / menus)
  python cli.py initdb      create an empty database from schema.sql
  python cli.py seed        (re)create database with demo data
Uses exactly the same service layer (services.py) as the web application.
"""
import getpass
import os
import sys
from datetime import datetime, timedelta

import services as S
from db import db_exists, init_db

if os.name == "nt":
    os.system("")          # enable ANSI colours on Windows terminals

C = {"b": "\033[1m", "dim": "\033[2m", "r": "\033[91m", "g": "\033[92m", "y": "\033[93m",
     "c": "\033[96m", "m": "\033[95m", "x": "\033[0m"}
STATUS_COL = {"approved": "g", "completed": "dim", "pending": "y", "rejected": "r", "cancelled": "r",
              "available": "g", "maintenance": "y", "retired": "r", "scheduled": "y", "in_progress": "c"}


def col(text, k):
    return f"{C[k]}{text}{C['x']}"


def st(s):
    return col(s, STATUS_COL.get(s, "x"))


def ask(prompt, default=None, secret=False):
    d = f" [{default}]" if default not in (None, "") else ""
    fn = getpass.getpass if secret else input
    v = fn(col(f"  {prompt}{d}: ", "c")).strip()
    return v if v else (default or "")


def banner(title):
    print("\n" + col("═" * 68, "c"))
    print(col(f"  {title}", "b"))
    print(col("═" * 68, "c"))


def table(headers, data):
    if not data:
        print(col("  (no records)", "dim")); return
    plain = lambda s: __import__("re").sub(r"\033\[[0-9;]*m", "", str(s))
    w = [max(len(plain(h)), *(len(plain(r[i])) for r in data)) for i, h in enumerate(headers)]
    line = "  " + "─┼─".join("─" * x for x in w)
    print("  " + col(" │ ".join(h.ljust(w[i]) for i, h in enumerate(headers)), "b"))
    print(line)
    for r in data:
        print("  " + " │ ".join(str(c) + " " * (w[i] - len(plain(c))) for i, c in enumerate(r)))
    print(col(f"\n  {len(data)} row(s)", "dim"))


def ok(msg): print(col(f"  ✔ {msg}", "g"))
def err(msg): print(col(f"  ✘ {msg}", "r"))


def pick_dept():
    depts = S.list_departments()
    for d in depts: print(f"    {d['dept_id']}. {d['name']}")
    return ask("Department number (blank to skip)")


def pick_when(default_day=None):
    day = ask("Date (YYYY-MM-DD)", default_day or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    st_, en = ask("Start time (HH:MM)", "10:00"), ask("End time   (HH:MM)", "11:00")
    return f"{day} {st_}", f"{day} {en}"


# ------------------------------------------------------------ screens
def show_dashboard(u):
    d = S.dashboard(u)["stats"]
    banner(f"DASHBOARD — {u['full_name']} ({u['role']})")
    print(f"  Resources: {col(d['resources'],'b')}   Free now: {col(d['available_now'],'g')}   In use: {col(d['in_use_now'],'c')}   "
          f"Under maintenance: {col(d['maintenance'],'y')}")
    print(f"  Bookings today: {col(d['today'],'b')}   Pending approvals: {col(d['pending'],'y')}   "
          f"Conflicts blocked by DB: {col(d['conflicts_blocked'],'r')}")
    up = S.dashboard(u)["upcoming"]
    if up:
        print(col("\n  Your upcoming bookings", "b"))
        table(["ID", "Resource", "Start", "End", "Status"], [[b["booking_id"], b["resource_name"], b["start_time"], b["end_time"][11:], st(b["status"])] for b in up])


def browse_resources(u):
    banner("BROWSE RESOURCES")
    types = S.list_types()
    for t in types: print(f"    {t['type_id']}. {t['icon']} {t['type_name']}")
    tid = ask("Filter by type number (blank = all)")
    q = ask("Search text (blank = none)")
    r = S.list_resources(tid or None, None, q or None)
    table(["ID", "Name", "Type", "Building", "Cap", "Status", "Equipment/Parent"],
          [[x["resource_id"], x["name"], x["type_name"], x["building"], x["capacity"], st(x["status"]),
            ", ".join(x["equipment"]) or (f"in {x['parent_name']}" if x["parent_name"] else "")] for x in r])


def find_available(u):
    banner("FIND AVAILABLE RESOURCES")
    s, e = pick_when()
    tid = ask("Type number (blank = all)")
    cap = ask("Minimum capacity", "0")
    r = S.availability(s, e, tid or None, cap)
    table(["ID", "Name", "Type", "Cap", "Availability"],
          [[x["resource_id"], x["name"], x["type_name"], x["capacity"], col("FREE", "g") if x["free"] else col(x["reason"], "r")] for x in r])


def book(u):
    banner("NEW BOOKING")
    rid = ask("Resource ID (use 'Browse' to look up)")
    s, e = pick_when()
    title = ask("Title / purpose")
    att = ask("Number of attendees", "1")
    try:
        b = S.create_booking(u, rid, title, s, e, att)
        ok(f"Booking #{b['booking_id']} created for {b['resource_name']} — status: {b['status'].upper()}")
        if b["status"] == "pending": print(col("  Waiting for admin approval.", "y"))
    except S.ServiceError as ex:
        err(ex.message)
        for a in ex.extra.get("alternatives", []): print(col(f"    ↳ Alternative room free then: #{a['resource_id']} {a['name']} (cap {a['capacity']})", "y"))
        for sl in ex.extra.get("next_slots", []): print(col(f"    ↳ Free slot on this resource: {sl['start']} – {sl['end'][11:]}", "y"))


def my_bookings(u, all_=False):
    banner("ALL BOOKINGS" if all_ else "MY BOOKINGS")
    status = ask("Filter by status (pending/approved/completed/cancelled/rejected, blank = all)")
    r = S.list_bookings(u, status or None, mine=not all_)[:40]
    table(["ID", "Resource", "By", "Title", "Start", "End", "Status"],
          [[x["booking_id"], x["resource_name"], x["user_name"], x["title"][:22], x["start_time"], x["end_time"][11:], st(x["status"])] for x in r])


def cancel(u):
    bid = ask("Booking ID to cancel")
    try:
        S.update_booking_status(u, int(bid), "cancelled"); ok("Booking cancelled")
    except (S.ServiceError, ValueError) as ex: err(getattr(ex, "message", "Enter a valid booking ID"))


def schedule(u):
    banner("RESOURCE DAY SCHEDULE")
    rid = ask("Resource ID")
    day = ask("Date (YYYY-MM-DD)", datetime.now().strftime("%Y-%m-%d"))
    try:
        s = S.resource_schedule(int(rid), day)
    except (S.ServiceError, ValueError) as ex:
        return err(getattr(ex, "message", "Invalid input"))
    print(f"  {s['resource']['icon']} {s['resource']['name']} — {day}  (open {s['open']}:00–{s['close']}:00)")
    items = [(b["start_time"], b["end_time"], f"{b['title']} — {b['user_name']}", b["status"]) for b in s["bookings"]] + \
            [(m["start_time"], m["end_time"], f"MAINTENANCE: {m['issue']}", "maintenance") for m in s["maintenance"]]
    table(["From", "To", "What", "Status"], [[a[11:] if a[:10] == day else a, b[11:] if b[:10] == day else b, w, st(x)] for a, b, w, x in sorted(items)])
    # text timeline
    bar = ["·"] * ((s["close"] - s["open"]) * 2)
    for a, b, _, x in items:
        a_, b_ = max(a, day + " 00:00"), min(b, day + " 23:59")
        i0 = int((int(a_[11:13]) - s["open"]) * 2 + int(a_[14:16]) / 30); i1 = int((int(b_[11:13]) - s["open"]) * 2 + (int(b_[14:16]) + 29) / 30)
        for i in range(max(i0, 0), min(i1, len(bar))): bar[i] = "█" if x != "maintenance" else "▒"
    print("\n  " + "".join(bar)); print("  " + "".join(str(h % 24).ljust(2)[:2] if True else "" for h in range(s["open"], s["close"]))[:len(bar)] + col("   █ booked  ▒ maintenance  · free", "dim"))


def approvals(u):
    banner("PENDING APPROVALS")
    r = S.list_bookings(u, "pending")
    r = sorted(r, key=lambda x: x["start_time"])
    table(["ID", "Resource", "By", "Role", "Title", "Start", "End"], [[x["booking_id"], x["resource_name"], x["user_name"], x["role"], x["title"][:20], x["start_time"], x["end_time"][11:]] for x in r])
    if not r: return
    bid = ask("Booking ID to act on (blank to go back)")
    if not bid: return
    act = ask("Action: (a)pprove / (r)eject", "a").lower()
    try:
        S.update_booking_status(u, int(bid), "approved" if act.startswith("a") else "rejected",
                                ask("Remarks (optional)") if act.startswith("r") else None)
        ok("Booking updated — user has been notified")
    except (S.ServiceError, ValueError) as ex: err(getattr(ex, "message", "Invalid booking ID"))


def add_resource(u):
    banner("ADD RESOURCE")
    for t in S.list_types(): print(f"    {t['type_id']}. {t['type_name']}")
    try:
        r = S.create_resource(u, {"name": ask("Name"), "type_id": ask("Type number"), "building": ask("Building"),
                                  "floor": ask("Floor", "0"), "capacity": ask("Capacity", "0"), "description": ask("Description")})
        ok(f"Resource '{r['name']}' added with ID {r['resource_id']}")
    except S.ServiceError as ex: err(ex.message)


def set_resource_status(u):
    rid = ask("Resource ID"); status = ask("New status (available/maintenance/retired)")
    try:
        r = S.update_resource(u, int(rid), {"status": status})
        ok(f"{r['name']} is now {r['status']}. {r['cancelled_bookings']} future booking(s) auto-cancelled.")
    except (S.ServiceError, ValueError) as ex: err(getattr(ex, "message", "Invalid input"))


def maintenance(u):
    banner("MAINTENANCE")
    m = S.list_maintenance()[:25]
    table(["ID", "Resource", "Issue", "From", "To", "Status"], [[x["maint_id"], x["resource_name"], x["issue"][:26], x["start_time"], x["end_time"], st(x["status"])] for x in m])
    c = ask("\n  (s)chedule new / (u)pdate status / blank to go back").lower()
    try:
        if c.startswith("s"):
            s, e = pick_when()
            r = S.create_maintenance(u, ask("Resource ID"), ask("Issue"), ask("Technician"), s, e)
            ok(f"Maintenance #{r['maint_id']} scheduled. {r['cancelled_bookings']} clashing booking(s) were auto-cancelled by the trigger.")
        elif c.startswith("u"):
            S.update_maintenance_status(u, int(ask("Maintenance ID")), ask("New status (in_progress/completed/cancelled)")); ok("Updated")
    except (S.ServiceError, ValueError) as ex: err(getattr(ex, "message", "Invalid input"))


def reports(u):
    r = S.reports(u)
    banner("UTILISATION REPORT")
    table(["Resource", "Type", "Bookings", "Hours"], [[x["name"], x["type_name"], x["total_bookings"], x["total_hours"]] for x in r["utilization"][:12]])
    print(col("\n  Usage by type", "b"))
    table(["Type", "Resources", "Bookings", "Hours"], [[x["type_name"], x["resources"], x["bookings"], x["hours"]] for x in r["by_type"]])
    print(col("\n  Peak hours", "b"))
    mx = max([p["bookings"] for p in r["peak_hours"]] or [1])
    for p in r["peak_hours"]: print(f"  {p['hour']:02d}:00  {col('█' * max(1, int(p['bookings'] * 30 / mx)), 'c')} {p['bookings']}")
    print(col(f"\n  Conflicting requests blocked by the database: {r['conflicts_blocked']}", "r"))
    if r["idle"]: print(col("  Never used: ", "b") + ", ".join(x["name"] for x in r["idle"]))


def audit(u):
    banner("AUDIT LOG (latest 25)")
    table(["#", "When", "Table", "Action", "Details"], [[x["log_id"], x["logged_at"], x["table_name"], x["action"], x["details"][:60]] for x in S.list_audit(u, 25)])


def users(u):
    banner("USERS")
    r = S.list_users(u)
    table(["ID", "Name", "Email", "Role", "Dept", "Bookings", "Active"], [[x["user_id"], x["full_name"], x["email"], x["role"], x["dept_name"] or "-", x["bookings"], "yes" if x["is_active"] else col("no", "r")] for x in r])


def notifications(u):
    banner("NOTIFICATIONS")
    n = S.list_notifications(u)
    for i in n["items"][:10]: print(f"  {col('●','y') if not i['is_read'] else ' '} {i['created_at']}  {i['message']}")
    if not n["items"]: print(col("  No notifications", "dim"))
    S.mark_notifications_read(u)


# ------------------------------------------------------------ menus
def main_menu(u):
    admin = u["role"] == "admin"
    items = [("Dashboard", show_dashboard), ("Browse resources", browse_resources), ("Find available resources", find_available),
             ("Book a resource", book), ("My bookings", my_bookings), ("Cancel a booking", cancel),
             ("Resource day schedule", schedule), ("Notifications", notifications)]
    if admin:
        items += [("[Admin] Pending approvals", approvals), ("[Admin] All bookings", lambda x: my_bookings(x, True)),
                  ("[Admin] Add resource", add_resource), ("[Admin] Change resource status", set_resource_status),
                  ("[Admin] Maintenance", maintenance), ("[Admin] Reports", reports),
                  ("[Admin] Audit log", audit), ("[Admin] Users", users)]
    items.append(("Logout", None))
    show_dashboard(u)
    while True:
        print(col("\n  MAIN MENU", "b"))
        for i, (label, _) in enumerate(items, 1): print(f"   {i:>2}. {label}")
        c = ask("Choose")
        if not c.isdigit() or not 1 <= int(c) <= len(items):
            err("Please enter a number from the menu"); continue
        label, fn = items[int(c) - 1]
        if fn is None: return
        try: fn(u)
        except KeyboardInterrupt: print()
        except S.ServiceError as ex: err(ex.message)


def do_register():
    banner("CREATE NEW ACCOUNT")
    try:
        u = S.register_user(ask("Full name"), ask("Email"), ask("Password (min 6 chars)", secret=True),
                            ask("Role (student/faculty/staff)", "student"), pick_dept(), ask("Phone (optional)"))
        ok(f"Welcome, {u['full_name']}! Account created and logged in.")
        return u
    except S.ServiceError as ex:
        err(ex.message)


def do_login():
    banner("LOGIN")
    try:
        return S.authenticate(ask("Email"), ask("Password", secret=True))
    except S.ServiceError as ex:
        err(ex.message)


def run():
    if not db_exists():
        print("No database found — creating demo data ..."); import seed; seed.run()
    print(col(r"""
   ____  __  __    _    ____ _____    ____    _    __  __ ____  _   _ ____
  / ___||  \/  |  / \  |  _ \_   _|  / ___|  / \  |  \/  |  _ \| | | / ___|
  \___ \| |\/| | / _ \ | |_) || |   | |     / _ \ | |\/| | |_) | | | \___ \
   ___) | |  | |/ ___ \|  _ < | |   | |___ / ___ \| |  | |  __/| |_| |___) |
  |____/|_|  |_/_/   \_\_| \_\|_|    \____/_/   \_\_|  |_|_|    \___/|____/
        Resource Allocation & Conflict Management System  (CLI)""", "c"))
    while True:
        print(col("\n  1. Login    2. Register new user    3. Exit", "b"))
        c = ask("Choose")
        u = do_login() if c == "1" else do_register() if c == "2" else None
        if c == "3": print("  Goodbye!"); return
        if u: main_menu(u)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "initdb": init_db(reset=True); print("Empty database created.")
    elif cmd == "seed": import seed; print(f"Seeded with {seed.run()} bookings.")
    else:
        try: run()
        except (KeyboardInterrupt, EOFError): print("\n  Bye!")
