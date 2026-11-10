"""Automated tests:  python tests.py     (uses a temporary database)"""
import os, tempfile, threading, unittest
from datetime import datetime, timedelta

os.environ["CAMPUS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
import seed, services as S           # noqa: E402
from db import connect               # noqa: E402

seed.run()
DAY = (datetime.now() + timedelta(days=40)).strftime("%Y-%m-%d")
slot = lambda a, b: (f"{DAY} {a}", f"{DAY} {b}")
U = {u["email"]: u for u in (S.authenticate(e, p) for e, p in
     [("admin@campus.edu", "admin123"), ("meera.rao@campus.edu", "faculty123"), ("rahul@campus.edu", "student123")])}
ADMIN, FAC, STU = U["admin@campus.edu"], U["meera.rao@campus.edu"], U["rahul@campus.edu"]


class Tests(unittest.TestCase):
    def test_register_and_login(self):
        u = S.register_user("Test User", "t@x.com", "secret1", "student", 1, "9876543210")
        self.assertEqual(S.authenticate("t@x.com", "secret1")["user_id"], u["user_id"])
        with self.assertRaises(S.ServiceError): S.register_user("Dup", "t@x.com", "secret1")        # unique email
        with self.assertRaises(S.ServiceError): S.register_user("Evil", "e@x.com", "secret1", "admin")  # no self-admin
        with self.assertRaises(S.ServiceError): S.authenticate("t@x.com", "wrong")

    def test_overlap_blocked_but_adjacent_allowed(self):
        a, b = slot("09:00", "10:00"); S.create_booking(FAC, 1, "A", a, b, 10)
        with self.assertRaises(S.ServiceError) as cm: S.create_booking(STU, 1, "B", *slot("09:30", "10:30"), 10)
        self.assertEqual(cm.exception.extra["kind"], "CONFLICT"); self.assertTrue(cm.exception.extra["next_slots"])
        S.create_booking(STU, 1, "C", *slot("10:00", "11:00"), 10)       # back-to-back is fine

    def test_database_trigger_blocks_raw_sql(self):
        import sqlite3
        S.create_booking(FAC, 2, "A", *slot("13:00", "14:00"), 5)
        with connect() as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("INSERT INTO bookings(resource_id,user_id,title,start_time,end_time,status) VALUES (2,2,'x',?,?,'approved')", slot("13:30", "14:30"))

    def test_capacity_and_check_constraints(self):
        with self.assertRaises(S.ServiceError): S.create_booking(FAC, 12, "Too many", *slot("09:00", "10:00"), 50)
        with self.assertRaises(S.ServiceError): S.create_booking(FAC, 3, "Backwards", *slot("11:00", "10:00"), 5)

    def test_maintenance_cascade_and_notification(self):
        b = S.create_booking(STU, 4, "Class", *slot("15:00", "16:00"), 10)
        r = S.create_maintenance(ADMIN, 4, "Repaint", "Crew", f"{DAY} 14:00", f"{DAY} 18:00")
        self.assertEqual(r["cancelled_bookings"], 1)
        self.assertEqual(S.get_booking(b["booking_id"])["status"], "cancelled")
        self.assertTrue(any("cancelled" in n["message"] for n in S.list_notifications(STU)["items"]))
        with self.assertRaises(S.ServiceError) as cm: S.create_booking(STU, 4, "Again", *slot("16:00", "17:00"), 5)
        self.assertEqual(cm.exception.extra["kind"], "MAINTENANCE")

    def test_approval_workflow_and_rbac(self):
        b = S.create_booking(STU, 5, "Lab", *slot("09:00", "10:00"), 10); self.assertEqual(b["status"], "pending")
        with self.assertRaises(S.ServiceError): S.update_booking_status(STU, b["booking_id"], "approved")   # students can't approve
        self.assertEqual(S.update_booking_status(ADMIN, b["booking_id"], "approved")["status"], "approved")
        with self.assertRaises(S.ServiceError): S.list_users(STU)

    def test_concurrent_bookings_only_one_wins(self):
        results = []
        def worker(i):
            try: S.create_booking(FAC, 7, f"T{i}", *slot("09:00", "10:00"), 5); results.append("ok")
            except S.ServiceError: results.append("blocked")
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(results.count("ok"), 1); self.assertEqual(results.count("blocked"), 9)

    def test_reports_and_audit(self):
        rep = S.reports(ADMIN); self.assertTrue(rep["utilization"]); self.assertGreaterEqual(rep["conflicts_blocked"], 1)
        self.assertTrue(S.list_audit(ADMIN))


if __name__ == "__main__":
    unittest.main(verbosity=2)
