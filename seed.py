"""Populate the database with realistic demo data."""
import random
from datetime import datetime, timedelta

import services as S
from db import connect, transaction, init_db

DEPTS = [("Computer Science & Engineering", "CSE"), ("Electronics & Communication", "ECE"),
         ("Mechanical Engineering", "MECH"), ("Physics", "PHY"), ("Administration", "ADM")]
TYPES = [("Classroom", "🏫", 0), ("Laboratory", "🔬", 0), ("Seminar Hall", "🎤", 0),
         ("Conference Room", "🗂️", 0), ("Equipment", "🎥", 1)]
# name, type, building, floor, capacity, description
ROOMS = [
    ("Classroom A-101", 1, "Academic Block A", 1, 60, "Tiered classroom with smart board"),
    ("Classroom A-102", 1, "Academic Block A", 1, 60, "Standard lecture room"),
    ("Classroom A-205", 1, "Academic Block A", 2, 80, "Large lecture room, dual projectors"),
    ("Classroom B-110", 1, "Academic Block B", 1, 45, "Tutorial room"),
    ("Computer Lab 1", 2, "Tech Block", 1, 40, "40 workstations, Linux & Windows"),
    ("Computer Lab 2", 2, "Tech Block", 1, 35, "GPU workstations"),
    ("Physics Lab", 2, "Science Block", 0, 30, "Optics and mechanics experiments"),
    ("Electronics Lab", 2, "Tech Block", 2, 30, "Oscilloscopes and signal generators"),
    ("Seminar Hall A", 3, "Main Building", 1, 150, "Stage, sound system, AC"),
    ("Seminar Hall B", 3, "Main Building", 2, 100, "Auditorium style seating"),
    ("Board Room", 4, "Admin Block", 3, 20, "Executive meeting room"),
    ("Discussion Room 1", 4, "Library", 1, 10, "Small group discussion room"),
]
# name, type, building, floor, description, parent room name
EQUIP = [
    ("Projector P-01", "Full HD projector", "Classroom A-101"),
    ("Projector P-02", "Full HD projector", "Seminar Hall A"),
    ("Smart Board SB-01", "75-inch interactive board", "Classroom A-205"),
    ("Portable Sound System", "Wireless mics + speakers", None),
    ("DSLR Camera Kit", "Event photography kit", None),
    ("VR Headset Set", "Set of 6 headsets", None),
]
USERS = [
    ("Priya Menon", "admin@campus.edu", "admin123", "admin", 5, "9000000001"),
    ("Dr. Meera Rao", "meera.rao@campus.edu", "faculty123", "faculty", 1, "9000000002"),
    ("Prof. Arjun Nair", "arjun.nair@campus.edu", "faculty123", "faculty", 2, "9000000003"),
    ("Kavita Sharma", "kavita@campus.edu", "staff123", "staff", 5, "9000000004"),
    ("Rahul Verma", "rahul@campus.edu", "student123", "student", 1, "9000000005"),
    ("Ananya Iyer", "ananya@campus.edu", "student123", "student", 2, "9000000006"),
    ("Sana Khan", "sana@campus.edu", "student123", "student", 4, "9000000007"),
]
TITLES = ["Data Structures Lecture", "DBMS Practical", "Guest Lecture", "Project Review", "Club Meeting", "Workshop",
          "Placement Training", "Research Seminar", "Exam Revision", "Hackathon Briefing", "Department Meeting"]


def run(reset=True):
    init_db(reset=reset)
    with connect() as c, transaction(c):
        c.executemany("INSERT INTO departments(name,code) VALUES (?,?)", DEPTS)
        c.executemany("INSERT INTO resource_types(type_name,icon,is_equipment) VALUES (?,?,?)", TYPES)
        for n, t, b, f, cap, d in ROOMS:
            c.execute("INSERT INTO resources(name,type_id,building,floor,capacity,description) VALUES (?,?,?,?,?,?)", (n, t, b, f, cap, d))
        for n, d, parent in EQUIP:
            pid = c.execute("SELECT resource_id, building, floor FROM resources WHERE name=?", (parent,)).fetchone() if parent else None
            c.execute("INSERT INTO resources(name,type_id,building,floor,capacity,description,parent_id) VALUES (?,?,?,?,0,?,?)",
                      (n, 5, pid["building"] if pid else "Central Store", pid["floor"] if pid else 0, d, pid["resource_id"] if pid else None))
    users = {}
    for n, e, p, r, d, ph in USERS:
        users[e] = S.register_user(n, e, p, r, d, ph, allow_admin=True)

    rng = random.Random(7)
    ids = [r["resource_id"] for r in S.list_resources()]
    people = [u for e, u in users.items() if u["role"] != "admin"]
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    made = 0
    for day_off in list(range(-14, 0)) + list(range(0, 8)):
        day = today + timedelta(days=day_off)
        if day.weekday() == 6: continue
        for _ in range(rng.randint(4, 7)):
            rid = rng.choice(ids)
            start_h = rng.choice([8, 9, 10, 11, 13, 14, 15, 16])
            dur = rng.choice([1, 1, 2, 2, 3])
            s, e = day + timedelta(hours=start_h), day + timedelta(hours=start_h + dur)
            u = rng.choice(people)
            res = S.get_resource(rid)
            att = max(1, min(res["capacity"] or 1, rng.randint(5, 50)))
            try:
                S.create_booking(u, rid, rng.choice(TITLES), S.fmt(s), S.fmt(e), att, allow_past=True,
                                 status="approved" if day_off < 0 else None)
                made += 1
            except S.ServiceError:
                pass   # a clash was correctly rejected by the DB - skip
    admin = users["admin@campus.edu"]
    now = datetime.now()
    by_name = {r["name"]: r for r in S.list_resources()}
    smart = by_name["Smart Board SB-01"]
    lab2 = by_name["Computer Lab 2"]
    S.create_maintenance(admin, smart["resource_id"], "Touch panel calibration", "TechServe Ltd", S.fmt(now - timedelta(hours=2)), S.fmt(now + timedelta(days=2)))
    S.create_maintenance(admin, lab2["resource_id"], "GPU driver upgrade & cooling check", "IT Services",
                         S.fmt((now + timedelta(days=4)).replace(hour=9, minute=0)), S.fmt((now + timedelta(days=4)).replace(hour=17, minute=0)))
    S.refresh_statuses()
    with connect() as c, transaction(c):
        c.execute("DELETE FROM notifications")   # start demo with a clean inbox
    return made


if __name__ == "__main__":
    n = run()
    print(f"Database seeded: {n} bookings created.")
    print("Login  ->  admin@campus.edu / admin123   |   meera.rao@campus.edu / faculty123   |   rahul@campus.edu / student123")
