"""
資料庫模組 - 使用 SQLite
包含：人員名單、空間、借用申請、假日、管理者設定
"""

import sqlite3
import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

DB_PATH = os.environ.get("LAB_BOOKING_DB", "/tmp/lab_booking.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_or_staff_id TEXT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            role TEXT DEFAULT 'student',
            unit TEXT,
            is_admin INTEGER DEFAULT 0,
            is_main_admin INTEGER DEFAULT 0,
            is_backup_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            only_holiday INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            space_id TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            applicant_name TEXT NOT NULL,
            applicant_email TEXT NOT NULL,
            purpose TEXT,
            phone TEXT,
            other_users TEXT,
            admin_note TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            holiday_date TEXT NOT NULL UNIQUE,
            name TEXT,
            is_typhoon INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(booking_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    # 預設空間
    spaces = [
        ("reading_room", "閱覽室", "僅開放星期六、日及國定假日", 1, 1),
        ("lab_common", "61302 共同實驗室", "僅開放平常上課／上班日", 0, 2),
        ("lab_discuss", "61302 小型討論室", "僅開放平常上課／上班日", 0, 3),
    ]
    for sid, name, desc, only_holiday, sort in spaces:
        cursor.execute("""
            INSERT OR IGNORE INTO spaces (id, name, description, only_holiday, sort_order)
            VALUES (?, ?, ?, ?, ?)
        """, (sid, name, desc, only_holiday, sort))

    conn.commit()
    conn.close()
  
def add_user(student_or_staff_id: str, name: str, email: str = None,
             role: str = "student", unit: str = None, is_admin: bool = False) -> bool:
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO users (student_or_staff_id, name, email, role, unit, is_admin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student_or_staff_id, name, email, role, unit, 1 if is_admin else 0))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_all_users(active_only: bool = True) -> List[Dict]:
    conn = get_connection()
    query = "SELECT * FROM users"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY name"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def find_user_by_email(email: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_slot_status(space_id: str, booking_date: str, time_slot: str) -> str:
    conn = get_connection()
    row = conn.execute("""
        SELECT status FROM bookings
        WHERE space_id = ? AND booking_date = ? AND time_slot = ?
        AND status IN ('pending', 'approved', 'cancel_requested')
        LIMIT 1
    """, (space_id, booking_date, time_slot)).fetchone()
    conn.close()
    if row:
        return row["status"] if row["status"] != "cancel_requested" else "approved"
    return "available"

def create_booking(data: Dict) -> str:
    import uuid
    booking_id = str(uuid.uuid4())[:8]
    conn = get_connection()
    conn.execute("""
        INSERT INTO bookings (
            id, space_id, booking_date, time_slot, status,
            applicant_name, applicant_email, purpose, phone, other_users
        ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
    """, (
        booking_id, data["space_id"], data["booking_date"], data["time_slot"],
        data["applicant_name"], data["applicant_email"],
        data.get("purpose", ""), data.get("phone", ""), data.get("other_users", "")
    ))
    conn.commit()
    conn.close()
    return booking_id

def get_bookings_by_status(status: str = None) -> List[Dict]:
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM bookings WHERE status = ? ORDER BY booking_date, time_slot", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM bookings ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_booking_status(booking_id: str, status: str, admin_note: str = "", reviewed_by: str = ""):
    conn = get_connection()
    conn.execute("""
        UPDATE bookings
        SET status = ?, admin_note = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ?
        WHERE id = ?
    """, (status, admin_note, reviewed_by, datetime.now().isoformat(),
          datetime.now().isoformat(), booking_id))
    conn.commit()
    conn.close()

def add_holiday(holiday_date: str, name: str = "", is_typhoon: bool = False):
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO holidays (holiday_date, name, is_typhoon)
            VALUES (?, ?, ?)
        """, (holiday_date, name, 1 if is_typhoon else 0))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def is_holiday(check_date: str) -> bool:
    d = datetime.strptime(check_date, "%Y-%m-%d").date()
    if d.weekday() >= 5:
        return True
    conn = get_connection()
    row = conn.execute("SELECT id FROM holidays WHERE holiday_date = ?", (check_date,)).fetchone()
    conn.close()
    return row is not None

def get_all_holidays() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM holidays ORDER BY holiday_date").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_holiday(holiday_date: str) -> bool:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM holidays WHERE holiday_date = ?", (holiday_date,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def add_holidays_bulk(dates: list, name: str = "國定假日") -> int:
    count = 0
    for d in dates:
        if add_holiday(d, name):
            count += 1
    return count

def set_vacation_period(vacation_type: str, start_date: str, end_date: str):
    conn = get_connection()
    key_start = f"{vacation_type}_vacation_start"
    key_end = f"{vacation_type}_vacation_end"
    now = datetime.now().isoformat()
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                 (key_start, start_date, now))
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                 (key_end, end_date, now))
    conn.commit()
    conn.close()

def get_vacation_period(vacation_type: str) -> Optional[Dict]:
    conn = get_connection()
    start = conn.execute("SELECT value FROM settings WHERE key = ?",
                         (f"{vacation_type}_vacation_start",)).fetchone()
    end = conn.execute("SELECT value FROM settings WHERE key = ?",
                       (f"{vacation_type}_vacation_end",)).fetchone()
    conn.close()
    if start and end:
        return {"start": start["value"], "end": end["value"]}
    return None

def is_in_vacation(check_date: str) -> bool:
    for vtype in ["winter", "summer"]:
        period = get_vacation_period(vtype)
        if period and period["start"] <= check_date <= period["end"]:
            return True
    return False

def is_reading_room_open(check_date: str) -> bool:
    d = datetime.strptime(check_date, "%Y-%m-%d").date()
    if d.weekday() >= 5:
        return True
    if is_holiday(check_date):
        return True
    if is_in_vacation(check_date):
        return True
    return False

def get_approved_for_access(days_ahead: int = 30) -> List[Dict]:
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=days_ahead)).isoformat()
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM bookings
        WHERE status = 'approved'
          AND booking_date >= ?
          AND booking_date <= ?
        ORDER BY booking_date, time_slot, space_id
    """, (today, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def export_access_list_text(days_ahead: int = 30) -> str:
    items = get_approved_for_access(days_ahead)
    if not items:
        return "目前沒有需要開通門禁的已核准申請。"

    space_names = {
        "reading_room": "閱覽室",
        "lab_common": "61302 共同實驗室",
        "lab_discuss": "61302 小型討論室"
    }
    lines = []
    lines.append("=" * 50)
    lines.append("需開通門禁名單")
    lines.append(f"產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 50)
    lines.append("")

    current_date = None
    for b in items:
        if b["booking_date"] != current_date:
            current_date = b["booking_date"]
            lines.append(f"【{current_date}】")
        space = space_names.get(b["space_id"], b["space_id"])
        lines.append(f"  ● {b['time_slot']}｜{space}")
        lines.append(f"    申請人：{b['applicant_name']}（{b['applicant_email']}）")
        if b.get("phone"):
            lines.append(f"    電話：{b['phone']}")
        if b.get("other_users"):
            lines.append(f"    其他使用者：{b['other_users']}")
        lines.append(f"    用途：{b.get('purpose') or '-'}")
        lines.append("")

    lines.append("=" * 50)
    lines.append(f"共 {len(items)} 筆")
    return "\n".join(lines)

if __name__ == "__main__":
    init_db()
    print("資料庫初始化完成")
