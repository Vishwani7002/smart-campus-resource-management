"""Database connection helpers (SQLite)."""
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CAMPUS_DB", os.path.join(BASE_DIR, "campus.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


@contextmanager
def connect():
    """Open a connection with foreign keys ON. isolation_level=None => we control
    transactions explicitly (BEGIN IMMEDIATE ... COMMIT) for ACID behaviour."""
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn):
    """ACID transaction. BEGIN IMMEDIATE takes the write lock up-front so two users
    can never insert overlapping bookings at the same moment (serialisable)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def db_exists():
    return os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0


def init_db(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with connect() as conn:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
