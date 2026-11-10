"""
Service layer - ALL business logic lives here.
Both the Flask web API (app.py) and the command-line app (cli.py) call these
functions, so the rules are identical everywhere.
"""
import hashlib
import hmac
import os
import re
import sqlite3
from datetime import datetime, timedelta

from db import connect, transaction

OPEN_H, CLOSE_H = 7, 22            # campus hours 07:00 - 22:00
ACTIVE = ("pending", "approved")
SELF_ROLES = ("student", "faculty", "staff")
FMT = "%Y-%m-%d %H:%M"


class ServiceError(Exception):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra or {}


# ------------------------------------------------------------ helpers
def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def fmt(dt):
    return dt.strftime(FMT)


def now_str():
    return fmt(datetime.now())


def parse_dt(value, label="time"):
    if not value:
        raise ServiceError(f"{label} is required")
    v = str(value).strip().replace("T", " ")[:16]
    try:
        return datetime.strptime(v, FMT)
    except ValueError:
        raise ServiceError(f"Invalid {label}. Use format YYYY-MM-DD HH:MM")


def require_admin(user):
    if not user or user["role"] != "admin":
        raise ServiceError("Admin access required", 403)


def validate_slot(s, e, allow_past=False):
    if e <= s:
        raise ServiceError("End time must be after start time")
    if s.date() != e.date():
        raise ServiceError("A booking must start and end on the same day")
    if (e - s) < timedelta(minutes=15):
        raise ServiceError("Minimum booking duration is 15 minutes")
    if (e - s) > timedelta(hours=12):
        raise ServiceError("Maximum booking duration is 12 hours")
    if s.hour < OPEN_H or (e.hour * 60 + e.minute) > CLOSE_H * 60:
        raise ServiceError(f"Campus hours are {OPEN_H:02d}:00 - {CLOSE_H:02d}:00")
    if not allow_past and s < datetime.now() - timedelta(minutes=5):
        raise ServiceError("Cannot book a time slot in the past")


def db_error(ex):
    """Translate trigger / constraint errors into a (kind, message) pair."""
    msg = str(ex)
    for tag in ("CONFLICT", "UNAVAILABLE", "CAPACITY", "MAINTENANCE"):
        if msg.startswith(tag + ":"):
            return tag, msg.split(":", 1)[1].strip()
    if "UNIQUE" in msg:
        return "UNIQUE", "A record with the same unique value already exists"
    if "FOREIGN KEY" in msg:
        return "FK", "Operation blocked: related records exist (foreign key constraint)"
    if "CHECK" in msg:
        return "CHECK", "Invalid data (check constraint failed)"
    return "DB", msg


# ------------------------------------------------------------ passwords
def hash_password(pw, salt=None):
    salt = salt or os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${dk}"


def verify_password(pw, stored):
    salt, dk = stored.split("$")
    return hmac.compare_digest(hash_password(pw, salt).split("$")[1], dk)


# ------------------------------------------------------------ lookups
def list_departments():
    with connect() as c:
        return rows(c.execute("SELECT * FROM departments ORDER BY name"))


def list_types():
    with connect() as c:
        return rows(c.execute("SELECT * FROM resource_types ORDER BY type_id"))


# ------------------------------------------------------------ users
def _public_user(r):
    r = dict(r)
    r.pop("password_hash", None)
    return r


def get_user(uid):
    with connect() as c:
        r = c.execute(
            "SELECT u.*, d.name AS dept_name FROM users u "
            "LEFT JOIN departments d ON d.dept_id=u.dept_id WHERE u.user_id=? AND u.is_active=1",
            (uid,),
        ).fetchone()
    return _public_user(r) if r else None


def register_user(full_name, email, password, role="student", dept_id=None, phone=None, allow_admin=False):
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    role = (role or "student").strip().lower()
    if len(full_name) < 2:
        raise ServiceError("Full name must be at least 2 characters")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ServiceError("Enter a valid email address")
    if len(password or "") < 6:
        raise ServiceError("Password must be at least 6 characters")
    if role not in SELF_ROLES and not (allow_admin and role == "admin"):
        raise ServiceError("Role must be student, faculty or staff")
    phone = (phone or "").strip() or None
    if phone and not re.match(r"^[0-9+\-\s]{7,15}$", phone):
        raise ServiceError("Enter a valid phone number")
    dept_id = int(dept_id) if dept_id not in (None, "", 0, "0") else None
    with connect() as c:
        try:
            with transaction(c):
                cur = c.execute(
                    "INSERT INTO users(full_name,email,password_hash,role,dept_id,phone) VALUES (?,?,?,?,?,?)",
                    (full_name, email, hash_password(password), role, dept_id, phone),
                )
                uid = cur.lastrowid
        except sqlite3.IntegrityError as ex:
            kind, msg = db_error(ex)
            raise ServiceError("This email is already registered" if kind == "UNIQUE" else msg, 409 if kind == "UNIQUE" else 400)
    return get_user(uid)


def authenticate(email, password):
    with connect() as c:
        r = c.execute("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),)).fetchone()
    if not r or not verify_password(password or "", r["password_hash"]):
        raise ServiceError("Invalid email or password", 401)
    if not r["is_active"]:
        raise ServiceError("Your account has been deactivated. Contact the administrator.", 403)
    return get_user(r["user_id"])


def list_users(admin):
    require_admin(admin)
    with connect() as c:
        return rows(c.execute(
            "SELECT u.user_id,u.full_name,u.email,u.role,u.phone,u.is_active,u.created_at,d.name AS dept_name,"
            "(SELECT COUNT(*) FROM bookings b WHERE b.user_id=u.user_id) AS bookings "
            "FROM users u LEFT JOIN departments d ON d.dept_id=u.dept_id ORDER BY u.created_at DESC"))


def set_user_active(admin, uid, active):
    require_admin(admin)
    if uid == admin["user_id"]:
        raise ServiceError("You cannot deactivate your own account")
    with connect() as c:
        with transaction(c):
            c.execute("UPDATE users SET is_active=? WHERE user_id=?", (1 if active else 0, uid))


# ------------------------------------------------------------ status refresh
def refresh_statuses():
    """Housekeeping (acts like a scheduled job): completes past bookings,
    expires stale pending requests, advances maintenance state."""
    n = now_str()
    with connect() as c:
        with transaction(c):
            c.execute("UPDATE maintenance SET status='in_progress' WHERE status='scheduled' AND start_time<=? AND end_time>?", (n, n))
            c.execute("UPDATE maintenance SET status='completed' WHERE status IN ('scheduled','in_progress') AND end_time<=?", (n,))
            c.execute("UPDATE bookings SET status='completed' WHERE status='approved' AND end_time<=?", (n,))
            c.execute("UPDATE bookings SET status='cancelled', remarks='Auto-cancelled: expired before approval' "
                      "WHERE status='pending' AND start_time<=?", (n,))


# ------------------------------------------------------------ resources
def list_resources(type_id=None, status=None, q=None):
    sql = ("SELECT r.*, t.type_name, t.icon, t.is_equipment, p.name AS parent_name "
           "FROM resources r JOIN resource_types t ON t.type_id=r.type_id "
           "LEFT JOIN resources p ON p.resource_id=r.parent_id WHERE 1=1")
    args = []
    if type_id:
        sql += " AND r.type_id=?"; args.append(int(type_id))
    if status:
        sql += " AND r.status=?"; args.append(status)
    if q:
        sql += " AND (r.name LIKE ? OR r.building LIKE ? OR r.description LIKE ?)"; args += [f"%{q}%"] * 3
    sql += " ORDER BY t.type_id, r.name"
    with connect() as c:
        res = rows(c.execute(sql, args))
        kids = {}
        for k in c.execute("SELECT parent_id, name FROM resources WHERE parent_id IS NOT NULL AND status<>'retired'"):
            kids.setdefault(k["parent_id"], []).append(k["name"])
    for r in res:
        r["equipment"] = kids.get(r["resource_id"], [])
    return res


def get_resource(rid):
    with connect() as c:
        r = c.execute("SELECT r.*, t.type_name, t.icon FROM resources r JOIN resource_types t USING(type_id) WHERE resource_id=?", (rid,)).fetchone()
    if not r:
        raise ServiceError("Resource not found", 404)
    return dict(r)


def _clean_resource(d, partial=False):
    out = {}
    if "name" in d or not partial:
        n = (d.get("name") or "").strip()
        if len(n) < 2: raise ServiceError("Resource name is required")
        out["name"] = n
    if "type_id" in d or not partial:
        try: out["type_id"] = int(d.get("type_id"))
        except (TypeError, ValueError): raise ServiceError("Choose a resource type")
    if "building" in d or not partial:
        b = (d.get("building") or "").strip()
        if not b: raise ServiceError("Building is required")
        out["building"] = b
    for k in ("floor", "capacity"):
        if k in d or not partial:
            try: out[k] = int(d.get(k) or 0)
            except ValueError: raise ServiceError(f"{k.title()} must be a number")
            if k == "capacity" and out[k] < 0: raise ServiceError("Capacity cannot be negative")
    if "status" in d:
        if d["status"] not in ("available", "maintenance", "retired"): raise ServiceError("Invalid status")
        out["status"] = d["status"]
    if "description" in d: out["description"] = (d.get("description") or "").strip() or None
    if "parent_id" in d: out["parent_id"] = int(d["parent_id"]) if d.get("parent_id") not in (None, "", 0, "0") else None
    return out


def create_resource(admin, data):
    require_admin(admin)
    d = _clean_resource(data)
    cols = ", ".join(d); marks = ", ".join("?" * len(d))
    with connect() as c:
        try:
            with transaction(c):
                rid = c.execute(f"INSERT INTO resources({cols}) VALUES ({marks})", list(d.values())).lastrowid
        except sqlite3.IntegrityError as ex:
            raise ServiceError(db_error(ex)[1], 409)
    return get_resource(rid)


def update_resource(admin, rid, data):
    require_admin(admin)
    get_resource(rid)
    d = _clean_resource(data, partial=True)
    if not d: raise ServiceError("Nothing to update")
    cancelled = 0
    with connect() as c:
        try:
            with transaction(c):
                sets = ", ".join(f"{k}=?" for k in d)
                c.execute(f"UPDATE resources SET {sets} WHERE resource_id=?", list(d.values()) + [rid])
                if d.get("status") in ("maintenance", "retired"):   # cascade: free up future bookings
                    cancelled = c.execute(
                        "UPDATE bookings SET status='cancelled', remarks='Auto-cancelled: resource taken out of service' "
                        "WHERE resource_id=? AND status IN ('pending','approved') AND end_time>?", (rid, now_str())).rowcount
        except sqlite3.IntegrityError as ex:
            raise ServiceError(db_error(ex)[1], 409)
    out = get_resource(rid); out["cancelled_bookings"] = cancelled
    return out


def delete_resource(admin, rid):
    require_admin(admin)
    with connect() as c:
        try:
            with transaction(c):
                c.execute("DELETE FROM resources WHERE resource_id=?", (rid,))
        except sqlite3.IntegrityError:
            raise ServiceError("This resource has booking history and cannot be deleted. Retire it instead.", 409)


# ------------------------------------------------------------ availability
def availability(start, end, type_id=None, min_capacity=0, only_free=False, exclude=None):
    s, e = parse_dt(start, "start time"), parse_dt(end, "end time")
    if e <= s: raise ServiceError("End time must be after start time")
    s, e = fmt(s), fmt(e)
    sql = """
    SELECT r.*, t.type_name, t.icon,
      (SELECT b.title || ' (' || substr(b.start_time,12) || '-' || substr(b.end_time,12) || ')'
         FROM bookings b WHERE b.resource_id=r.resource_id AND b.status IN ('pending','approved')
          AND b.start_time < :e AND b.end_time > :s LIMIT 1) AS busy_booking,
      (SELECT m.issue FROM maintenance m WHERE m.resource_id=r.resource_id
          AND m.status IN ('scheduled','in_progress') AND m.start_time < :e AND m.end_time > :s LIMIT 1) AS busy_maint
    FROM resources r JOIN resource_types t ON t.type_id=r.type_id
    WHERE r.status <> 'retired' AND r.capacity >= :cap AND (:tid IS NULL OR r.type_id = :tid)
    ORDER BY t.type_id, r.name"""
    with connect() as c:
        res = rows(c.execute(sql, {"s": s, "e": e, "cap": int(min_capacity or 0), "tid": int(type_id) if type_id else None}))
    out = []
    for r in res:
        if r["status"] == "maintenance": r["reason"] = "Out of service (maintenance)"
        elif r["busy_maint"]: r["reason"] = f"Maintenance: {r['busy_maint']}"
        elif r["busy_booking"]: r["reason"] = f"Booked: {r['busy_booking']}"
        else: r["reason"] = None
        r["free"] = r["reason"] is None
        if exclude and r["resource_id"] == int(exclude): continue
        if only_free and not r["free"]: continue
        out.append(r)
    return out


def free_slots(resource_id, start, end, limit=3):
    """Gap-finding algorithm: next free windows (same length) on that day."""
    s, e = parse_dt(start), parse_dt(end)
    dur = e - s
    day = s.strftime("%Y-%m-%d")
    open_t = datetime.strptime(f"{day} {OPEN_H:02d}:00", FMT)
    close_t = datetime.strptime(f"{day} {CLOSE_H:02d}:00", FMT)
    with connect() as c:
        busy = [(r[0], r[1]) for r in c.execute(
            "SELECT start_time,end_time FROM bookings WHERE resource_id=? AND status IN ('pending','approved') AND start_time LIKE ? "
            "UNION ALL SELECT start_time,end_time FROM maintenance WHERE resource_id=? AND status IN ('scheduled','in_progress') "
            "AND start_time < ? AND end_time > ? ORDER BY 1", (resource_id, day + "%", resource_id, day + " 23:59", day + " 00:00"))]
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = max(open_t, datetime.now() + timedelta(minutes=1)) if day == today else open_t
    free = []                                   # list of free windows (gap_start, gap_end)
    for bs, be in sorted(busy):
        bs = max(datetime.strptime(bs, FMT), open_t)
        be = min(datetime.strptime(be, FMT), close_t) if be[:10] == day else close_t
        if bs - cursor >= dur:
            free.append((cursor, bs))
        cursor = max(cursor, be)
    if close_t - cursor >= dur:
        free.append((cursor, close_t))
    # inside each free window pick the slot nearest to the time the user wanted
    slots = [min(max(s, g0), g1 - dur) for g0, g1 in free]
    slots.sort(key=lambda g: abs((g - s).total_seconds()))
    return [{"start": fmt(g), "end": fmt(g + dur)} for g in slots[:limit]]


# ------------------------------------------------------------ bookings
def create_booking(user, resource_id, title, start, end, attendees=1, allow_past=False, status=None):
    s, e = parse_dt(start, "start time"), parse_dt(end, "end time")
    validate_slot(s, e, allow_past)
    title = (title or "").strip()
    if not title: raise ServiceError("Please enter a title / purpose")
    try: attendees = int(attendees or 1)
    except ValueError: raise ServiceError("Attendees must be a number")
    if attendees < 1: raise ServiceError("Attendees must be at least 1")
    res = get_resource(int(resource_id))
    status = status or ("approved" if user["role"] in ("admin", "faculty") else "pending")
    with connect() as c:
        try:
            with transaction(c):     # ACID: atomic + isolated
                bid = c.execute(
                    "INSERT INTO bookings(resource_id,user_id,title,start_time,end_time,attendees,status) VALUES (?,?,?,?,?,?,?)",
                    (res["resource_id"], user["user_id"], title, fmt(s), fmt(e), attendees, status)).lastrowid
        except sqlite3.IntegrityError as ex:
            kind, msg = db_error(ex)
            extra = {"kind": kind}
            if kind in ("CONFLICT", "MAINTENANCE"):
                extra["next_slots"] = free_slots(res["resource_id"], fmt(s), fmt(e))
                alts = availability(fmt(s), fmt(e), res["type_id"], attendees, only_free=True, exclude=res["resource_id"])
                extra["alternatives"] = [{"resource_id": a["resource_id"], "name": a["name"], "capacity": a["capacity"], "building": a["building"]} for a in alts[:4]]
                with transaction(c):  # log the blocked attempt for reporting
                    c.execute("INSERT INTO audit_log(table_name,record_id,action,details) VALUES ('bookings',NULL,'CONFLICT_BLOCKED',?)",
                              (f"{user['full_name']} tried {res['name']} {fmt(s)}-{fmt(e)[11:]}: {msg}",))
            raise ServiceError(msg, 409 if kind in ("CONFLICT", "MAINTENANCE") else 400, extra)
    return get_booking(bid)


def get_booking(bid):
    with connect() as c:
        r = c.execute("SELECT * FROM v_booking_details WHERE booking_id=?", (bid,)).fetchone()
    if not r: raise ServiceError("Booking not found", 404)
    return dict(r)


def list_bookings(user, status=None, mine=False, resource_id=None, limit=300):
    refresh_statuses()
    sql, args = "SELECT * FROM v_booking_details WHERE 1=1", []
    if user["role"] != "admin" or mine:
        sql += " AND user_id=?"; args.append(user["user_id"])
    if status: sql += " AND status=?"; args.append(status)
    if resource_id: sql += " AND resource_id=?"; args.append(int(resource_id))
    sql += " ORDER BY start_time DESC LIMIT ?"; args.append(limit)
    with connect() as c:
        return rows(c.execute(sql, args))


def update_booking_status(user, bid, new_status, remarks=None):
    b = get_booking(bid)
    is_owner = b["user_id"] == user["user_id"]
    if new_status in ("approved", "rejected"):
        require_admin(user)
        if b["status"] != "pending": raise ServiceError("Only pending bookings can be approved or rejected")
    elif new_status == "cancelled":
        if not (is_owner or user["role"] == "admin"): raise ServiceError("You can only cancel your own bookings", 403)
        if b["status"] not in ACTIVE: raise ServiceError("Only pending or approved bookings can be cancelled")
    else:
        raise ServiceError("Invalid status")
    with connect() as c:
        try:
            with transaction(c):
                c.execute("UPDATE bookings SET status=?, remarks=? WHERE booking_id=?",
                          (new_status, (remarks or "").strip() or (f"Cancelled by {user['full_name']}" if new_status == "cancelled" and not is_owner else None), bid))
        except sqlite3.IntegrityError as ex:
            raise ServiceError(db_error(ex)[1], 409)
    return get_booking(bid)


def resource_schedule(resource_id, date):
    parse_dt(date + " 00:00")
    with connect() as c:
        bk = rows(c.execute("SELECT booking_id,title,user_name,start_time,end_time,status,attendees FROM v_booking_details "
                            "WHERE resource_id=? AND start_time LIKE ? AND status IN ('pending','approved','completed') ORDER BY start_time",
                            (resource_id, date + "%")))
        mt = rows(c.execute("SELECT maint_id,issue,technician,start_time,end_time,status FROM maintenance "
                            "WHERE resource_id=? AND status IN ('scheduled','in_progress','completed') AND start_time < ? AND end_time > ?",
                            (resource_id, date + " 23:59", date + " 00:00")))
    return {"resource": get_resource(resource_id), "bookings": bk, "maintenance": mt, "open": OPEN_H, "close": CLOSE_H}


# ------------------------------------------------------------ maintenance
def list_maintenance(status=None):
    refresh_statuses()
    sql = ("SELECT m.*, r.name AS resource_name, t.icon, u.full_name AS created_by_name FROM maintenance m "
           "JOIN resources r ON r.resource_id=m.resource_id JOIN resource_types t ON t.type_id=r.type_id "
           "LEFT JOIN users u ON u.user_id=m.created_by")
    args = []
    if status: sql += " WHERE m.status=?"; args.append(status)
    sql += " ORDER BY m.start_time DESC"
    with connect() as c:
        return rows(c.execute(sql, args))


def create_maintenance(admin, resource_id, issue, technician, start, end):
    require_admin(admin)
    s, e = parse_dt(start, "start time"), parse_dt(end, "end time")
    if e <= s: raise ServiceError("End time must be after start time")
    if not (issue or "").strip(): raise ServiceError("Describe the maintenance issue")
    get_resource(int(resource_id))
    status = "in_progress" if s <= datetime.now() < e else "scheduled"
    with connect() as c:
        try:
            with transaction(c):
                affected = c.execute(
                    "SELECT COUNT(*) FROM bookings WHERE resource_id=? AND status IN ('pending','approved') AND start_time<? AND end_time>?",
                    (resource_id, fmt(e), fmt(s))).fetchone()[0]
                mid = c.execute("INSERT INTO maintenance(resource_id,issue,technician,start_time,end_time,status,created_by) VALUES (?,?,?,?,?,?,?)",
                                (resource_id, issue.strip(), (technician or "").strip() or None, fmt(s), fmt(e), status, admin["user_id"])).lastrowid
        except sqlite3.IntegrityError as ex:
            raise ServiceError(db_error(ex)[1])
    return {"maint_id": mid, "status": status, "cancelled_bookings": affected}


def update_maintenance_status(admin, mid, new_status):
    require_admin(admin)
    if new_status not in ("in_progress", "completed", "cancelled"): raise ServiceError("Invalid status")
    with connect() as c:
        with transaction(c):
            c.execute("UPDATE maintenance SET status=? WHERE maint_id=?", (new_status, mid))


# ------------------------------------------------------------ notifications
def list_notifications(user):
    with connect() as c:
        items = rows(c.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY notif_id DESC LIMIT 30", (user["user_id"],)))
    return {"items": items, "unread": sum(1 for i in items if not i["is_read"])}


def mark_notifications_read(user):
    with connect() as c:
        with transaction(c):
            c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user["user_id"],))


# ------------------------------------------------------------ dashboard & reports
def dashboard(user):
    refresh_statuses()
    n, today = now_str(), datetime.now().strftime("%Y-%m-%d")
    admin = user["role"] == "admin"
    scope, sargs = ("", []) if admin else (" AND user_id=?", [user["user_id"]])
    with connect() as c:
        one = lambda q, a=(): c.execute(q, a).fetchone()[0]
        stats = {
            "resources": one("SELECT COUNT(*) FROM resources WHERE status<>'retired'"),
            "available_now": one("SELECT COUNT(*) FROM resources r WHERE r.status='available' AND NOT EXISTS "
                                 "(SELECT 1 FROM bookings b WHERE b.resource_id=r.resource_id AND b.status='approved' AND b.start_time<=? AND b.end_time>?)", (n, n)),
            "in_use_now": one("SELECT COUNT(DISTINCT resource_id) FROM bookings WHERE status='approved' AND start_time<=? AND end_time>?", (n, n)),
            "maintenance": one("SELECT COUNT(*) FROM resources WHERE status='maintenance'"),
            "pending": one("SELECT COUNT(*) FROM bookings WHERE status='pending'" + scope, sargs),
            "today": one("SELECT COUNT(*) FROM bookings WHERE status IN ('pending','approved','completed') AND start_time LIKE ?" + scope, [today + "%"] + sargs),
            "conflicts_blocked": one("SELECT COUNT(*) FROM audit_log WHERE action='CONFLICT_BLOCKED'"),
            "total_bookings": one("SELECT COUNT(*) FROM bookings WHERE 1=1" + scope, sargs),
        }
        todays = rows(c.execute("SELECT * FROM v_booking_details WHERE status IN ('pending','approved','completed') AND start_time LIKE ?" + scope + " ORDER BY start_time", [today + "%"] + sargs))
        upcoming = rows(c.execute("SELECT * FROM v_booking_details WHERE user_id=? AND status IN ('pending','approved') AND start_time>=? ORDER BY start_time LIMIT 5", (user["user_id"], n)))
        top = rows(c.execute("SELECT name,icon,total_hours,total_bookings FROM v_resource_utilization ORDER BY total_hours DESC LIMIT 6"))
    return {"stats": stats, "today": todays, "upcoming": upcoming, "top": top}


def reports(admin):
    require_admin(admin)
    refresh_statuses()
    with connect() as c:
        return {
            "utilization": rows(c.execute("SELECT * FROM v_resource_utilization ORDER BY total_hours DESC")),
            "by_type": rows(c.execute(
                "SELECT t.type_name, t.icon, COUNT(DISTINCT r.resource_id) AS resources, COUNT(b.booking_id) AS bookings, "
                "ROUND(COALESCE(SUM((julianday(b.end_time)-julianday(b.start_time))*24),0),1) AS hours "
                "FROM resource_types t LEFT JOIN resources r ON r.type_id=t.type_id "
                "LEFT JOIN bookings b ON b.resource_id=r.resource_id AND b.status IN ('approved','completed') GROUP BY t.type_id")),
            "peak_hours": rows(c.execute(
                "SELECT CAST(strftime('%H', start_time) AS INTEGER) AS hour, COUNT(*) AS bookings FROM bookings "
                "WHERE status IN ('approved','completed') GROUP BY hour ORDER BY hour")),
            "top_users": rows(c.execute(
                "SELECT u.full_name, u.role, COUNT(*) AS bookings FROM bookings b JOIN users u ON u.user_id=b.user_id "
                "WHERE b.status IN ('approved','completed') GROUP BY u.user_id HAVING COUNT(*) >= 1 ORDER BY bookings DESC LIMIT 5")),
            "by_dept": rows(c.execute(
                "SELECT COALESCE(d.name,'Unassigned') AS dept, COUNT(*) AS bookings FROM bookings b JOIN users u ON u.user_id=b.user_id "
                "LEFT JOIN departments d ON d.dept_id=u.dept_id WHERE b.status IN ('approved','completed') GROUP BY dept ORDER BY bookings DESC")),
            "by_status": rows(c.execute("SELECT status, COUNT(*) AS count FROM bookings GROUP BY status")),
            "idle": rows(c.execute(  # subquery: resources never booked
                "SELECT name, type_name FROM v_resource_utilization WHERE resource_id NOT IN "
                "(SELECT DISTINCT resource_id FROM bookings WHERE status IN ('approved','completed')) AND status<>'retired'")),
            "conflicts_blocked": c.execute("SELECT COUNT(*) FROM audit_log WHERE action='CONFLICT_BLOCKED'").fetchone()[0],
        }


def list_audit(admin, limit=150):
    require_admin(admin)
    with connect() as c:
        return rows(c.execute("SELECT * FROM audit_log ORDER BY log_id DESC LIMIT ?", (limit,)))
