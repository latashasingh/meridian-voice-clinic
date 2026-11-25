"""Mock clinic data store and booking logic.

Used by both the voice bot (as tool implementations) and the dashboard API.
State lives in a SQLite file, so the two processes always see the same data.

Rules enforced here (not only in the prompt):
- a caller is identified only by the 10-digit phone number they speak
- one active appointment per phone number
- a slot can only be booked once
- past slots can never be booked
"""

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "clinic.db"

DOCTORS = [
    (1, "Dr. Ananya Sharma", "Cardiology"),
    (2, "Dr. Rohan Mehta", "Dermatology"),
    (3, "Dr. Priya Nair", "Pediatrics"),
    (4, "Dr. Vikram Singh", "Orthopedics"),
    (5, "Dr. Sana Khan", "General Medicine"),
]
SLOT_TIMES = ["10:00", "10:30", "11:00", "14:00", "15:30", "17:00"]
DAYS_AHEAD = 7


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and make sure upcoming slots exist. Safe to call repeatedly."""
    with _db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                speciality TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                time TEXT NOT NULL,
                UNIQUE (doctor_id, day, time)
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                time TEXT NOT NULL,
                phone TEXT NOT NULL,
                patient_name TEXT,
                status TEXT NOT NULL DEFAULT 'booked',
                created_at TEXT NOT NULL,
                cancelled_at TEXT
            );
            """
        )
        db.executemany("INSERT OR IGNORE INTO doctors (id, name, speciality) VALUES (?, ?, ?)", DOCTORS)
        today = date.today()
        for offset in range(DAYS_AHEAD + 1):
            d = today + timedelta(days=offset)
            if d.weekday() == 6:  # the clinic is closed on Sundays
                continue
            for doctor_id, _, _ in DOCTORS:
                for t in SLOT_TIMES:
                    db.execute(
                        "INSERT OR IGNORE INTO slots (doctor_id, day, time) VALUES (?, ?, ?)",
                        (doctor_id, d.isoformat(), t),
                    )


def reset_appointments() -> None:
    """Remove all appointments (handy before recording the demo video)."""
    with _db() as db:
        db.execute("DELETE FROM appointments")


# --------------------------------------------------------------------------
# Parsing and formatting helpers
# --------------------------------------------------------------------------


def normalize_phone(raw: str) -> str | None:
    """Return a clean 10-digit number, or None if the input is not valid."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _normalize_time(raw: str) -> str | None:
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", (raw or "").lower())
    if not m:
        return None
    hour, minute, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _valid_day(raw: str) -> str | None:
    try:
        return date.fromisoformat((raw or "").strip()).isoformat()
    except ValueError:
        return None


def _label(day: str, time: str) -> str:
    d = date.fromisoformat(day)
    t = datetime.strptime(time, "%H:%M")
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}, {t.strftime('%I:%M %p').lstrip('0')}"


def _is_past(day: str, time: str) -> bool:
    return datetime.fromisoformat(f"{day}T{time}") <= datetime.now()


def _match_doctors(db, doctor: str = "", speciality: str = "") -> list[sqlite3.Row]:
    rows = db.execute("SELECT * FROM doctors ORDER BY id").fetchall()
    if doctor:
        words = [w for w in re.sub(r"[^a-z ]", " ", doctor.lower()).split() if w != "dr"]
        rows = [r for r in rows if all(w in r["name"].lower() for w in words)]
    if speciality:
        s = speciality.lower().strip()
        rows = [r for r in rows if s in r["speciality"].lower() or r["speciality"].lower() in s]
    return rows


def _open_slots(db, doctor_id: int, day: str | None = None) -> list[tuple[str, str]]:
    query = """
        SELECT s.day, s.time FROM slots s
        WHERE s.doctor_id = ? AND s.day >= ?
          AND NOT EXISTS (
              SELECT 1 FROM appointments a
              WHERE a.doctor_id = s.doctor_id AND a.day = s.day
                AND a.time = s.time AND a.status = 'booked'
          )
    """
    args: list = [doctor_id, date.today().isoformat()]
    if day:
        query += " AND s.day = ?"
        args.append(day)
    query += " ORDER BY s.day, s.time"
    return [(r["day"], r["time"]) for r in db.execute(query, args).fetchall() if not _is_past(r["day"], r["time"])]


def _appointment_view(row: sqlite3.Row, doctor_name: str, speciality: str) -> dict:
    return {
        "appointment_id": row["id"],
        "doctor": doctor_name,
        "speciality": speciality,
        "date": row["day"],
        "time": row["time"],
        "when": _label(row["day"], row["time"]),
        "phone": row["phone"],
        "status": row["status"],
    }


# --------------------------------------------------------------------------
# Tool implementations (called by the voice bot)
# --------------------------------------------------------------------------


def check_availability(doctor: str = "", speciality: str = "", day: str = "", limit: int = 6) -> dict:
    """Open slots for matching doctors, optionally on one date (YYYY-MM-DD)."""
    if day:
        day = _valid_day(day)
        if not day:
            return {"success": False, "error": "invalid_date", "message": "Date must be YYYY-MM-DD."}
    with _db() as db:
        doctors = _match_doctors(db, doctor, speciality)
        if not doctors:
            everyone = [f"{r['name']} ({r['speciality']})" for r in db.execute("SELECT * FROM doctors")]
            return {
                "success": False,
                "error": "no_matching_doctor",
                "message": "No doctor matches that request.",
                "available_doctors": everyone,
            }
        results = []
        for d in doctors:
            slots = _open_slots(db, d["id"], day or None)[:limit]
            results.append(
                {
                    "doctor": d["name"],
                    "speciality": d["speciality"],
                    "open_slots": [{"date": s[0], "time": s[1], "when": _label(*s)} for s in slots],
                }
            )
    return {"success": True, "searched_date": day or "next 7 days", "doctors": results}


def book(doctor: str, day: str, time: str, phone: str, patient_name: str = "") -> dict:
    """Book one slot for the caller identified by phone number."""
    clean_phone = normalize_phone(phone)
    if not clean_phone:
        return {"success": False, "error": "invalid_phone", "message": "Phone number must have 10 digits."}
    day, time_norm = _valid_day(day), _normalize_time(time)
    if not day or not time_norm:
        return {"success": False, "error": "invalid_datetime", "message": "Use YYYY-MM-DD and HH:MM."}
    if _is_past(day, time_norm):
        return {"success": False, "error": "slot_in_past", "message": "That time has already passed."}

    with _db() as db:
        matches = _match_doctors(db, doctor)
        if len(matches) != 1:
            return {"success": False, "error": "doctor_not_found", "message": "Doctor name is not specific enough."}
        doc = matches[0]

        existing = db.execute(
            "SELECT * FROM appointments WHERE phone = ? AND status = 'booked'", (clean_phone,)
        ).fetchone()
        if existing:
            doc_row = db.execute("SELECT * FROM doctors WHERE id = ?", (existing["doctor_id"],)).fetchone()
            return {
                "success": False,
                "error": "already_has_appointment",
                "message": "This number already has an active appointment. Cancel it first to book another.",
                "existing_appointment": _appointment_view(existing, doc_row["name"], doc_row["speciality"]),
            }

        slot = db.execute(
            "SELECT 1 FROM slots WHERE doctor_id = ? AND day = ? AND time = ?", (doc["id"], day, time_norm)
        ).fetchone()
        if not slot:
            return {"success": False, "error": "slot_does_not_exist", "message": "That slot is not offered."}
        taken = db.execute(
            "SELECT 1 FROM appointments WHERE doctor_id = ? AND day = ? AND time = ? AND status = 'booked'",
            (doc["id"], day, time_norm),
        ).fetchone()
        if taken:
            return {"success": False, "error": "slot_taken", "message": "That slot was just taken."}

        cur = db.execute(
            "INSERT INTO appointments (doctor_id, day, time, phone, patient_name, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'booked', ?)",
            (doc["id"], day, time_norm, clean_phone, patient_name.strip() or None, datetime.now().isoformat()),
        )
        row = db.execute("SELECT * FROM appointments WHERE id = ?", (cur.lastrowid,)).fetchone()
        return {"success": True, "appointment": _appointment_view(row, doc["name"], doc["speciality"])}


def cancel(phone: str) -> dict:
    """Cancel the active appointment that belongs to this phone number."""
    clean_phone = normalize_phone(phone)
    if not clean_phone:
        return {"success": False, "error": "invalid_phone", "message": "Phone number must have 10 digits."}
    with _db() as db:
        row = db.execute(
            "SELECT * FROM appointments WHERE phone = ? AND status = 'booked' ORDER BY id DESC", (clean_phone,)
        ).fetchone()
        if not row:
            return {"success": False, "error": "no_appointment", "message": "No active appointment for this number."}
        db.execute(
            "UPDATE appointments SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
            (datetime.now().isoformat(), row["id"]),
        )
        doc = db.execute("SELECT * FROM doctors WHERE id = ?", (row["doctor_id"],)).fetchone()
        cancelled = db.execute("SELECT * FROM appointments WHERE id = ?", (row["id"],)).fetchone()
        return {"success": True, "cancelled_appointment": _appointment_view(cancelled, doc["name"], doc["speciality"])}


# --------------------------------------------------------------------------
# Read helpers for the dashboard API
# --------------------------------------------------------------------------


def doctors_overview() -> list[dict]:
    """Every doctor with all upcoming open slots."""
    with _db() as db:
        out = []
        for d in db.execute("SELECT * FROM doctors ORDER BY id").fetchall():
            slots = _open_slots(db, d["id"])
            out.append(
                {
                    "id": d["id"],
                    "name": d["name"],
                    "speciality": d["speciality"],
                    "slots": [{"date": s[0], "time": s[1], "when": _label(*s)} for s in slots],
                }
            )
        return out


def appointments_overview() -> list[dict]:
    """All appointments, newest first (cancelled ones included)."""
    with _db() as db:
        rows = db.execute(
            "SELECT a.*, d.name AS doctor_name, d.speciality AS doctor_speciality "
            "FROM appointments a JOIN doctors d ON d.id = a.doctor_id ORDER BY a.id DESC"
        ).fetchall()
        return [_appointment_view(r, r["doctor_name"], r["doctor_speciality"]) for r in rows]
