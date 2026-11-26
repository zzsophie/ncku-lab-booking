"""
系實驗室 / 閱覽室 借用系統
公開查詢 + 模擬登入 + 申請 + 我的申請 + 管理者審核 + 門禁名單
"""
from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import date, timedelta, datetime
from functools import wraps
import sys, os, uuid

sys.path.insert(0, os.path.dirname(__file__))

from utils.database import (
    init_db, get_slot_status, is_reading_room_open, is_holiday,
    create_booking, get_bookings_by_status, update_booking_status,
    export_access_list_text, get_connection
)

init_db()
app = Flask(__name__)
app.secret_key = "ncku-lab-booking-secret-key-2026"

SPACES = {
    "reading_room": "閱覽室",
    "lab_common": "61302 共同實驗室",
    "lab_discuss": "61302 小型討論室"
}
TIME_SLOTS = ["上午", "下午", "晚間"]


def can_book_space(space_id, d):
    date_str = d.strftime("%Y-%m-%d")
    if space_id == "reading_room":
        return is_reading_room_open(date_str)
    return d.weekday() < 5 and not is_holiday(date_str)


def status_text(s):
    return {
        "available": "✅ 可借用",
        "pending": "🟡 待審核",
        "approved": "🔴 已核准",
        "rejected": "❌ 已拒絕",
        "cancelled": "⚪ 已取消",
        "cancel_requested": "🟠 取消申請中",
    }.get(s, s)


def current_user():
    return session.get("user")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ==================== 公開查詢 ====================
PUBLIC_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>系實驗室 / 閱覽室 借用查詢</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; color: #222; }
    .header { background: #1a365d; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
    .header h1 { margin: 0; font-size: 1.3rem; }
    .header a { color: #a0aec0; text-decoration: none; margin-left: 12px; font-size: 0.9rem; }
    .container { max-width: 960px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }
    select { padding: 8px 12px; border-radius: 8px; border: 1px solid #cbd5e0; font-size: 1rem; max-width: 320px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { padding: 10px 8px; text-align: center; border-bottom: 1px solid #e2e8f0; }
    th { background: #edf2f7; }
    td:first-child, th:first-child { text-align: left; }
    .weekend { color: #2b6cb0; }
    .btn { display: inline-block; background: #2b6cb0; color: white; padding: 10px 18px; border-radius: 8px; text-decoration: none; font-weight: 600; border: none; cursor: pointer; }
    .btn-outline { background: transparent; border: 1px solid #2b6cb0; color: #2b6cb0; }
    .info { background: #ebf8ff; border-left: 4px solid #3182ce; padding: 12px 16px; margin: 12px 0; border-radius: 0 8px 8px 0; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🏫 系實驗室 / 閱覽室 借用查詢</h1>
      <p style="margin:4px 0 0;opacity:0.85;font-size:0.9rem;">成功大學｜公開查詢</p>
    </div>
    <div>
      {% if user %}
        <span style="margin-right:8px;">{{ user.name }}</span>
        <a href="{{ url_for('my_bookings') }}">我的申請</a>
        <a href="{{ url_for('apply') }}">新增申請</a>
        {% if user.is_admin %}<a href="{{ url_for('admin') }}">管理者後台</a>{% endif %}
        <a href="{{ url_for('logout') }}">登出</a>
      {% else %}
        <a href="{{ url_for('login') }}">登入</a>
      {% endif %}
    </div>
  </div>
  <div class="container">
    <div class="card">
      <form method="get">
        <label><strong>請選擇空間</strong></label><br>
        <select name="space" onchange="this.form.submit()">
          {% for sid, sname in spaces.items() %}
            <option value="{{ sid }}" {% if sid == space_id %}selected{% endif %}>{{ sname }}</option>
          {% endfor %}
        </select>
      </form>
      <div class="info">
        目前選擇：<strong>{{ spaces[space_id] }}</strong><br>
        {% if space_id == "reading_room" %}
          📌 開放日：週末、國定假日、寒暑假期間
        {% else %}
          📌 僅開放平常上課／上班日
        {% endif %}
      </div>
    </div>
    <div class="card">
      <h2 style="margin-top:0;font-size:1.1rem;">📅 {{ today }} ～ {{ end_date }}</h2>
      <table>
        <thead><tr><th>日期</th><th>上午</th><th>下午</th><th>晚間</th></tr></thead>
        <tbody>
          {% for row in rows %}
          <tr>
            <td class="{% if row.weekend %}weekend{% endif %}">{% if row.weekend %}🏖️ {% endif %}{{ row.label }}</td>
            {% for cell in row.slots %}<td>{{ cell }}</td>{% endfor %}
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <p style="margin-top:16px;">✅ 可借用　🟡 待審核　🔴 已核准　🚫 不開放</p>
    </div>
    <div class="card">
      {% if user %}
        <a class="btn" href="{{ url_for('apply') }}">➡️ 前往新增申請</a>
      {% else %}
        <a class="btn" href="{{ url_for('login') }}">➡️ 登入並申請借用</a>
      {% endif %}
      <a class="btn btn-outline" href="{{ url_for('access_list') }}" style="margin-left:8px;">🔑 門禁開通名單</a>
    </div>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    space_id = request.args.get("space", "reading_room")
    if space_id not in SPACES:
        space_id = "reading_room"
    today = date.today()
    end = today + timedelta(days=30)
    rows = []
    for i in range(31):
        d = today + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        weekday = ["一", "二", "三", "四", "五", "六", "日"][d.weekday()]
        label = f"{date_str}（{weekday}）"
        slots = []
        for slot in TIME_SLOTS:
            if not can_book_space(space_id, d):
                slots.append("🚫 不開放")
            else:
                st = get_slot_status(space_id, date_str, slot)
                slots.append(status_text(st))
        rows.append({"label": label, "weekend": d.weekday() >= 5, "slots": slots})
    return render_template_string(
        PUBLIC_TEMPLATE,
        spaces=SPACES,
        space_id=space_id,
        today=today.isoformat(),
        end_date=end.isoformat(),
        rows=rows,
        user=current_user()
    )


# ==================== 登入（測試用模擬） ====================
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>登入</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .container { max-width: 420px; margin: 40px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    input[type=text], input[type=email] { width: 100%; padding: 10px; margin: 8px 0 16px; border: 1px solid #cbd5e0; border-radius: 8px; box-sizing: border-box; }
    .btn { background: #2b6cb0; color: white; padding: 12px; border: none; border-radius: 8px; width: 100%; font-weight: 600; cursor: pointer; }
    a { color: #2b6cb0; }
  </style>
</head>
<body>
  <div class="header"><h1 style="margin:0;font-size:1.3rem;">🔑 登入系統</h1></div>
  <div class="container">
    <div class="card">
      <p>目前為<strong>測試用模擬登入</strong>。正式版會改為 Google 登入。</p>
      <form method="post">
        <label>姓名</label>
        <input type="text" name="name" value="測試使用者" required>
        <label>Email</label>
        <input type="email" name="email" value="test@gs.ncku.edu.tw" required>
        <label><input type="checkbox" name="is_admin" value="1"> 我是管理者（測試用）</label>
        <br><br>
        <button class="btn" type="submit">模擬登入</button>
      </form>
      <p style="margin-top:16px;"><a href="{{ url_for('index') }}">← 返回公開查詢</a></p>
    </div>
  </div>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        is_admin = request.form.get("is_admin") == "1"
        if name and email:
            session["user"] = {
                "name": name,
                "email": email,
                "is_admin": is_admin,
                "is_main_admin": is_admin
            }
            return redirect(url_for("apply"))
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ==================== 新增申請 ====================
APPLY_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>新增申請</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .container { max-width: 640px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 16px; }
    label { font-weight: 600; display: block; margin: 12px 0 4px; }
    input, select, textarea { width: 100%; padding: 10px; border: 1px solid #cbd5e0; border-radius: 8px; box-sizing: border-box; }
    textarea { min-height: 80px; }
    .btn { background: #2b6cb0; color: white; padding: 12px 24px; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; margin-top: 16px; }
    .slot-group { margin: 8px 0; padding: 8px; background: #f7fafc; border-radius: 8px; }
    .msg { padding: 12px; border-radius: 8px; margin-bottom: 16px; }
    .success { background: #c6f6d5; }
    .error { background: #fed7d7; }
    a { color: #2b6cb0; }
  </style>
</head>
<body>
  <div class="header"><h1 style="margin:0;font-size:1.3rem;">📝 新增借用申請</h1></div>
  <div class="container">
    {% if message %}<div class="msg {{ msg_type }}">{{ message }}</div>{% endif %}
    <div class="card">
      <p>申請人：{{ user.name }}（{{ user.email }}）</p>
      <form method="post">
        <label>選擇空間 *</label>
        <select name="space_id" required>
          {% for sid, sname in spaces.items() %}
            <option value="{{ sid }}">{{ sname }}</option>
          {% endfor %}
        </select>
        <label>選擇日期 *（最早明天）</label>
        <input type="date" name="dates" min="{{ min_date }}" max="{{ max_date }}" required>
        <label>時段 *（可多選）</label>
        <div class="slot-group">
          {% for slot in time_slots %}
            <label style="font-weight:normal;"><input type="checkbox" name="slots" value="{{ slot }}"> {{ slot }}</label>
          {% endfor %}
        </div>
        <label>姓名 *</label>
        <input type="text" name="name" value="{{ user.name }}" required>
        <label>用途 *</label>
        <textarea name="purpose" required placeholder="請簡述借用目的"></textarea>
        <label>聯絡電話 *</label>
        <input type="text" name="phone" required placeholder="09xx-xxx-xxx">
        <label>其他使用者（人數 + 學號或姓名）</label>
        <textarea name="other_users" placeholder="若需幫其他人開通門禁，請務必填寫"></textarea>
        <button class="btn" type="submit">送出申請</button>
      </form>
    </div>
    <p><a href="{{ url_for('index') }}">← 返回查詢</a>　<a href="{{ url_for('my_bookings') }}">我的申請</a></p>
  </div>
</body>
</html>
"""


@app.route("/apply", methods=["GET", "POST"])
@login_required
def apply():
    user = current_user()
    message, msg_type = None, ""
    today = date.today()
    min_date = (today + timedelta(days=1)).isoformat()
    max_date = (today + timedelta(days=30)).isoformat()

    if request.method == "POST":
        space_id = request.form.get("space_id")
        date_str = request.form.get("dates")
        slots = request.form.getlist("slots")
        name = request.form.get("name", "").strip()
        purpose = request.form.get("purpose", "").strip()
        phone = request.form.get("phone", "").strip()
        other_users = request.form.get("other_users", "").strip()

        if not all([space_id, date_str, slots, name, purpose, phone]):
            message, msg_type = "請填寫所有必填欄位並選擇至少一個時段", "error"
        else:
            d = date.fromisoformat(date_str)
            if not can_book_space(space_id, d):
                message, msg_type = "所選日期依空間規則不開放借用", "error"
            else:
                count = 0
                for slot in slots:
                    if get_slot_status(space_id, date_str, slot) == "available":
                        create_booking({
                            "space_id": space_id,
                            "booking_date": date_str,
                            "time_slot": slot,
                            "applicant_name": name,
                            "applicant_email": user["email"],
                            "purpose": purpose,
                            "phone": phone,
                            "other_users": other_users
                        })
                        count += 1
                if count:
                    message, msg_type = f"已成功送出 {count} 筆申請，狀態為待審核。", "success"
                else:
                    message, msg_type = "所選時段皆無法申請（可能已被占用）", "error"

    return render_template_string(
        APPLY_TEMPLATE,
        user=user,
        spaces=SPACES,
        time_slots=TIME_SLOTS,
        min_date=min_date,
        max_date=max_date,
        message=message,
        msg_type=msg_type
    )


# ==================== 我的申請 ====================
MY_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>我的申請</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .container { max-width: 720px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 12px; }
    .btn { background: #e53e3e; color: white; padding: 6px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9rem; }
    a { color: #2b6cb0; }
  </style>
</head>
<body>
  <div class="header"><h1 style="margin:0;font-size:1.3rem;">📋 我的申請</h1></div>
  <div class="container">
    <p>{{ user.name }} 的申請紀錄</p>
    {% if not bookings %}
      <div class="card">目前沒有申請紀錄。<a href="{{ url_for('apply') }}">前往新增申請</a></div>
    {% else %}
      {% for b in bookings %}
      <div class="card">
        <strong>{{ b.booking_date }} {{ b.time_slot }}</strong>｜{{ spaces.get(b.space_id, b.space_id) }}<br>
        狀態：{{ status_text(b.status) }}<br>
        用途：{{ b.purpose or '-' }}<br>
        {% if b.admin_note %}管理員備註：{{ b.admin_note }}<br>{% endif %}
        {% if b.status == 'pending' %}
          <form method="post" style="display:inline;margin-top:8px;">
            <input type="hidden" name="booking_id" value="{{ b.id }}">
            <input type="hidden" name="action" value="cancel">
            <button class="btn" type="submit">取消申請</button>
          </form>
        {% elif b.status == 'approved' %}
          <form method="post" style="display:inline;margin-top:8px;">
            <input type="hidden" name="booking_id" value="{{ b.id }}">
            <input type="hidden" name="action" value="request_cancel">
            <button class="btn" type="submit">申請取消借用</button>
          </form>
        {% endif %}
      </div>
      {% endfor %}
    {% endif %}
    <p><a href="{{ url_for('index') }}">← 返回查詢</a>　<a href="{{ url_for('apply') }}">新增申請</a></p>
  </div>
</body>
</html>
"""


@app.route("/my-bookings", methods=["GET", "POST"])
@login_required
def my_bookings():
    user = current_user()
    if request.method == "POST":
        bid = request.form.get("booking_id")
        action = request.form.get("action")
        if action == "cancel":
            update_booking_status(bid, "cancelled")
        elif action == "request_cancel":
            update_booking_status(bid, "cancel_requested")
        return redirect(url_for("my_bookings"))

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM bookings WHERE applicant_email = ? ORDER BY booking_date DESC",
        (user["email"],)
    ).fetchall()
    conn.close()
    bookings = [dict(r) for r in rows]
    return render_template_string(
        MY_TEMPLATE,
        user=user,
        bookings=bookings,
        spaces=SPACES,
        status_text=status_text
    )


# ==================== 管理者後台 ====================
ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>管理者後台</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .container { max-width: 800px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 12px; }
    .btn { padding: 8px 14px; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; margin-right: 8px; }
    .btn-ok { background: #38a169; color: white; }
    .btn-no { background: #e53e3e; color: white; }
    input[type=text] { padding: 8px; border: 1px solid #cbd5e0; border-radius: 6px; width: 60%; }
    a { color: #2b6cb0; }
  </style>
</head>
<body>
  <div class="header"><h1 style="margin:0;font-size:1.3rem;">🛠️ 管理者後台</h1></div>
  <div class="container">
    <p>待審核：{{ pending|length }}　｜　取消申請待處理：{{ cancel_reqs|length }}</p>
    <h3>待審核列表</h3>
    {% if not pending %}
      <div class="card">目前沒有待審核申請</div>
    {% else %}
      {% for b in pending %}
      <div class="card">
        <strong>{{ b.booking_date }} {{ b.time_slot }}</strong>｜{{ spaces.get(b.space_id, b.space_id) }}<br>
        申請人：{{ b.applicant_name }}（{{ b.applicant_email }}）<br>
        用途：{{ b.purpose or '-' }}　電話：{{ b.phone or '-' }}<br>
        {% if b.other_users %}其他使用者：{{ b.other_users }}<br>{% endif %}
        <form method="post" style="margin-top:8px;">
          <input type="hidden" name="booking_id" value="{{ b.id }}">
          <input type="text" name="admin_note" placeholder="管理員備註（選填）">
          <br><br>
          <button class="btn btn-ok" name="action" value="approve" type="submit">✅ 核准</button>
          <button class="btn btn-no" name="action" value="reject" type="submit">❌ 拒絕</button>
        </form>
      </div>
      {% endfor %}
    {% endif %}
    <h3>取消申請待處理</h3>
    {% if not cancel_reqs %}
      <div class="card">目前沒有取消申請</div>
    {% else %}
      {% for b in cancel_reqs %}
      <div class="card">
        {{ b.booking_date }} {{ b.time_slot }}｜{{ b.applicant_name }}
        <form method="post" style="display:inline;">
          <input type="hidden" name="booking_id" value="{{ b.id }}">
          <button class="btn btn-no" name="action" value="confirm_cancel" type="submit">確認取消</button>
        </form>
      </div>
      {% endfor %}
    {% endif %}
    <p><a href="{{ url_for('index') }}">← 返回查詢</a>　<a href="{{ url_for('access_list') }}">門禁開通名單</a></p>
  </div>
</body>
</html>
"""


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    user = current_user()
    if not user.get("is_admin"):
        return "您沒有管理者權限", 403

    if request.method == "POST":
        bid = request.form.get("booking_id")
        action = request.form.get("action")
        note = request.form.get("admin_note", "")
        if action == "approve":
            update_booking_status(bid, "approved", note, user["email"])
        elif action == "reject":
            update_booking_status(bid, "rejected", note, user["email"])
        elif action == "confirm_cancel":
            update_booking_status(bid, "cancelled", reviewed_by=user["email"])
        return redirect(url_for("admin"))

    pending = get_bookings_by_status("pending")
    cancel_reqs = get_bookings_by_status("cancel_requested")
    return render_template_string(
        ADMIN_TEMPLATE,
        user=user,
        pending=pending,
        cancel_reqs=cancel_reqs,
        spaces=SPACES
    )


# ==================== 門禁開通名單 ====================
ACCESS_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>門禁開通名單</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .header a { color: #a0aec0; text-decoration: none; }
    .container { max-width: 800px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    pre { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; white-space: pre-wrap; }
    .btn { background: #2b6cb0; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
  </style>
</head>
<body>
  <div class="header">
    <h1 style="margin:0;font-size:1.3rem;">🔑 門禁開通名單</h1>
    <a href="{{ url_for('index') }}">← 返回公開查詢</a>
  </div>
  <div class="container">
    <div class="card">
      <p>以下為已核准且借用日在未來 30 天內的申請。</p>
      <button class="btn" onclick="navigator.clipboard.writeText(document.getElementById('list').innerText)">📋 複製全部名單</button>
      <pre id="list">{{ access_text }}</pre>
    </div>
  </div>
</body>
</html>
"""


@app.route("/access-list")
def access_list():
    text = export_access_list_text(30)
    return render_template_string(ACCESS_TEMPLATE, access_text=text)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8502))
    app.run(host="0.0.0.0", port=port, debug=False)
