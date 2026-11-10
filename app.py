"""Flask REST API + static frontend server.   Run:  python app.py"""
import os
from functools import wraps

from flask import Flask, jsonify, request, session, send_from_directory

import services as S
from db import db_exists

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY", "smart-campus-dev-secret")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def current_user():
    uid = session.get("uid")
    return S.get_user(uid) if uid else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            session.clear()
            return jsonify(error="Please log in to continue"), 401
        return fn(user, *a, **kw)
    return wrapper


@app.errorhandler(S.ServiceError)
def on_service_error(e):
    return jsonify(error=e.message, **e.extra), e.status


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found"), 404
    return send_from_directory("static", "index.html")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ---------------------------------------------------------------- auth
@app.post("/api/register")
def register():
    d = request.get_json(force=True, silent=True) or {}
    user = S.register_user(d.get("full_name"), d.get("email"), d.get("password"),
                           d.get("role", "student"), d.get("dept_id"), d.get("phone"))
    session["uid"] = user["user_id"]
    return jsonify(user), 201


@app.post("/api/login")
def login():
    d = request.get_json(force=True, silent=True) or {}
    user = S.authenticate(d.get("email"), d.get("password"))
    session["uid"] = user["user_id"]
    return jsonify(user)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@login_required
def me(user):
    return jsonify(user)


@app.get("/api/meta")
def meta():
    return jsonify(departments=S.list_departments(), types=S.list_types())


# ---------------------------------------------------------------- resources
@app.get("/api/resources")
@login_required
def resources(user):
    a = request.args
    return jsonify(S.list_resources(a.get("type_id"), a.get("status"), a.get("q")))


@app.post("/api/resources")
@login_required
def resource_create(user):
    return jsonify(S.create_resource(user, request.get_json(force=True))), 201


@app.put("/api/resources/<int:rid>")
@login_required
def resource_update(user, rid):
    return jsonify(S.update_resource(user, rid, request.get_json(force=True)))


@app.delete("/api/resources/<int:rid>")
@login_required
def resource_delete(user, rid):
    S.delete_resource(user, rid)
    return jsonify(ok=True)


@app.get("/api/resources/<int:rid>/schedule")
@login_required
def schedule(user, rid):
    S.refresh_statuses()
    return jsonify(S.resource_schedule(rid, request.args.get("date", "")))


@app.get("/api/availability")
@login_required
def availability(user):
    a = request.args
    S.refresh_statuses()
    return jsonify(S.availability(a.get("start"), a.get("end"), a.get("type_id"), a.get("capacity", 0)))


# ---------------------------------------------------------------- bookings
@app.get("/api/bookings")
@login_required
def bookings(user):
    a = request.args
    return jsonify(S.list_bookings(user, a.get("status"), a.get("mine") == "1", a.get("resource_id")))


@app.post("/api/bookings")
@login_required
def booking_create(user):
    d = request.get_json(force=True)
    b = S.create_booking(user, d.get("resource_id"), d.get("title"), d.get("start"), d.get("end"), d.get("attendees", 1))
    return jsonify(b), 201


@app.post("/api/bookings/<int:bid>/status")
@login_required
def booking_status(user, bid):
    d = request.get_json(force=True)
    return jsonify(S.update_booking_status(user, bid, d.get("status"), d.get("remarks")))


# ---------------------------------------------------------------- maintenance
@app.get("/api/maintenance")
@login_required
def maintenance(user):
    return jsonify(S.list_maintenance(request.args.get("status")))


@app.post("/api/maintenance")
@login_required
def maintenance_create(user):
    d = request.get_json(force=True)
    return jsonify(S.create_maintenance(user, d.get("resource_id"), d.get("issue"), d.get("technician"), d.get("start"), d.get("end"))), 201


@app.post("/api/maintenance/<int:mid>/status")
@login_required
def maintenance_status(user, mid):
    S.update_maintenance_status(user, mid, request.get_json(force=True).get("status"))
    return jsonify(ok=True)


# ---------------------------------------------------------------- misc
@app.get("/api/dashboard")
@login_required
def dashboard(user):
    return jsonify(S.dashboard(user))


@app.get("/api/reports")
@login_required
def reports(user):
    return jsonify(S.reports(user))


@app.get("/api/audit")
@login_required
def audit(user):
    return jsonify(S.list_audit(user))


@app.get("/api/users")
@login_required
def users(user):
    return jsonify(S.list_users(user))


@app.post("/api/users/<int:uid>/active")
@login_required
def user_active(user, uid):
    S.set_user_active(user, uid, bool(request.get_json(force=True).get("active")))
    return jsonify(ok=True)


@app.get("/api/notifications")
@login_required
def notifications(user):
    return jsonify(S.list_notifications(user))


@app.post("/api/notifications/read")
@login_required
def notifications_read(user):
    S.mark_notifications_read(user)
    return jsonify(ok=True)


if __name__ == "__main__":
    if not db_exists():
        import seed
        print("First run: creating database and demo data ...")
        seed.run()
    print("\n  Smart Campus is running ->  http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
