"""Runs docs/demo_queries.sql statement by statement and prints results.
Usage (from project folder):  python docs/run_demo_queries.py
Statements that SHOULD fail (trigger / CHECK demos) are shown in red."""
import os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import DB_PATH

conn = sqlite3.connect(DB_PATH); conn.execute("PRAGMA foreign_keys = ON")
text = open(os.path.join(os.path.dirname(__file__), "demo_queries.sql"), encoding="utf-8").read()
text = "\n".join(l for l in text.splitlines() if not l.startswith(".") and not l.startswith("PRAGMA"))
for n, stmt in enumerate([s.strip() for s in text.split(";") if s.strip()], 1):
    lines = [l for l in stmt.splitlines() if l.strip()]
    comment = next((l for l in lines if l.startswith("--")), "")
    print(f"\n\033[96m[{n}] {comment.lstrip('- ').strip()}\033[0m")
    print("    " + " ".join(l.strip() for l in lines if not l.startswith("--"))[:150])
    try:
        cur = conn.execute(stmt)
        rows = cur.fetchall()
        if cur.description:
            print("    " + " | ".join(d[0] for d in cur.description))
            for r in rows[:8]: print("    " + " | ".join(str(x) for x in r))
        else:
            print("    \033[92m✔ executed\033[0m")
    except sqlite3.Error as e:
        print(f"    \033[91m✘ REJECTED BY DATABASE: {e}\033[0m")
conn.commit()
