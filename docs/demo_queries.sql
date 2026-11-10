-- =====================================================================
--  DEMO QUERIES  (run in:  sqlite3 campus.db   then   .read docs/demo_queries.sql)
--  Handy to show the faculty that the DATABASE itself enforces the rules.
-- =====================================================================
.headers on
.mode column
PRAGMA foreign_keys = ON;

-- 1. JOIN: full booking details through a VIEW
SELECT booking_id, resource_name, user_name, start_time, end_time, status
FROM v_booking_details ORDER BY start_time DESC LIMIT 8;

-- 2. AGGREGATE + GROUP BY + HAVING: users with more than 3 confirmed bookings
SELECT u.full_name, COUNT(*) AS total
FROM bookings b JOIN users u ON u.user_id = b.user_id
WHERE b.status IN ('approved','completed')
GROUP BY u.user_id HAVING COUNT(*) > 3 ORDER BY total DESC;

-- 3. SUBQUERY (NOT EXISTS): rooms free for a given slot
SELECT r.name FROM resources r
WHERE r.status = 'available'
  AND NOT EXISTS (SELECT 1 FROM bookings b
                  WHERE b.resource_id = r.resource_id
                    AND b.status IN ('pending','approved')
                    AND b.start_time < '2026-12-01 11:00' AND b.end_time > '2026-12-01 10:00');

-- 4. SELF JOIN: equipment and the room it is installed in
SELECT e.name AS equipment, p.name AS installed_in
FROM resources e JOIN resources p ON p.resource_id = e.parent_id;

-- 5. VIEW: utilisation per resource
SELECT name, total_bookings, total_hours FROM v_resource_utilization ORDER BY total_hours DESC LIMIT 5;

-- 6. TRIGGER DEMO — conflict prevention. Run these two INSERTs one after another:
INSERT INTO bookings(resource_id,user_id,title,start_time,end_time,attendees,status)
VALUES (1, 2, 'First booking', '2030-01-10 10:00', '2030-01-10 11:00', 20, 'approved');
-- The next INSERT overlaps (10:30-11:30) => fails with "CONFLICT: Resource is already booked..."
INSERT INTO bookings(resource_id,user_id,title,start_time,end_time,attendees,status)
VALUES (1, 3, 'Overlapping booking', '2030-01-10 10:30', '2030-01-10 11:30', 20, 'approved');

-- 7. CHECK constraint demo: end before start is rejected
INSERT INTO bookings(resource_id,user_id,title,start_time,end_time)
VALUES (2, 2, 'Bad time', '2030-01-10 12:00', '2030-01-10 11:00');

-- 8. Audit trail written automatically by triggers
SELECT log_id, action, details, logged_at FROM audit_log ORDER BY log_id DESC LIMIT 6;

-- 9. Clean up the demo rows
DELETE FROM bookings WHERE start_time LIKE '2030-01-10%';
