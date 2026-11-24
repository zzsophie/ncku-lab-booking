"""
簡易 Flask 預覽版 - 公開查詢頁 + 門禁開通名單
"""
from flask import Flask, render_template_string, request
from datetime import date, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from utils.database import (
    init_db, get_slot_status, is_reading_room_open, is_holiday,
    get_approved_for_access, export_access_list_text
)

init_db()
app = Flask(__name__)
app.secret_key = "ncku-lab-preview-secret"

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
    }.get(s, s)

TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>系實驗室 / 閱覽室 借用查詢</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; color: #222; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .header h1 { margin: 0; font-size: 1.4rem; }
    .header p { margin: 4px 0 0; opacity: 0.85; font-size: 0.9rem; }
    .container { max-width: 960px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }
    label { font-weight: 600; display: block; margin-bottom: 6px; }
    select { padding: 8px 12px; border-radius: 8px; border: 1px solid #cbd5e0; font-size: 1rem; width: 100%; max-width: 320px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { padding: 10px 8px; text-align: center; border-bottom: 1px solid #e2e8f0; }
    th { background: #edf2f7; font-weight: 600; }
    td:first-child, th:first-child { text-align: left; }
    .weekend { color: #2b6cb0; }
    .legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 16px; font-size: 0.95rem; }
    .btn { display: inline-block; background: #2b6cb0; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 12px; }
    .btn:hover { background: #2c5282; }
    .info { background: #ebf8ff; border-left: 4px solid #3182ce; padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 12px 0; }
    .note { color: #718096; font-size: 0.9rem; margin-top: 24px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🏫 系實驗室 / 閱覽室 借用查詢</h1>
    <p>成功大學　｜　公開查詢（無需登入）</p>
  </div>
  <div class="container">
    <div class="card">
      <form method="get">
        <label>請選擇空間</label>
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
      <h2 style="margin-top:0; font-size:1.1rem;">📅 {{ today }} ～ {{ end_date }}</h2>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>上午</th>
            <th>下午</th>
            <th>晚間</th>
          </tr>
        </thead>
        <tbody>
          {% for row in rows %}
          <tr>
            <td class="{% if row.weekend %}weekend{% endif %}">
              {% if row.weekend %}🏖️ {% endif %}{{ row.label }}
            </td>
            {% for cell in row.slots %}
              <td>{{ cell }}</td>
            {% endfor %}
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <div class="legend">
        <span>✅ 可借用</span>
        <span>🟡 待審核</span>
        <span>🔴 已核准</span>
        <span>🚫 不開放</span>
      </div>
    </div>

    <div class="card">
      <p>想申請借用嗎？正式版本登入後即可申請。</p>
      <p><a class="btn" href="/access-list">🔑 查看門禁開通名單（管理者用）</a></p>
      <p class="note">此為預覽版。完整申請、審核、人員管理等功能已開發於系統中。</p>
    </div>
  </div>
</body>
</html>
"""

ACCESS_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>門禁開通名單</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif; margin: 0; background: #f5f7fa; color: #222; }
    .header { background: #1a365d; color: white; padding: 16px 24px; }
    .header h1 { margin: 0; font-size: 1.4rem; }
    .header a { color: #a0aec0; text-decoration: none; font-size: 0.9rem; }
    .container { max-width: 800px; margin: 24px auto; padding: 0 16px; }
    .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 20px; }
    pre { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; white-space: pre-wrap; font-size: 0.95rem; line-height: 1.5; }
    .btn { display: inline-block; background: #2b6cb0; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; border: none; cursor: pointer; font-size: 1rem; }
    .btn:hover { background: #2c5282; }
    .meta { color: #718096; font-size: 0.9rem; margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="header">
    <h1>🔑 門禁開通名單</h1>
    <a href="/">← 返回公開查詢</a>
  </div>
  <div class="container">
    <div class="card">
      <p class="meta">以下為「已核准」且借用日在未來 30 天內的申請，可直接複製到門禁系統對照使用。</p>
      <button class="btn" onclick="copyText()">📋 複製全部名單</button>
      <p id="msg" style="color:green; margin-top:8px;"></p>
      <pre id="list">{{ access_text }}</pre>
    </div>
  </div>
  <script>
    function copyText() {
      const text = document.getElementById('list').innerText;
      navigator.clipboard.writeText(text).then(function() {
        document.getElementById('msg').innerText = '已複製到剪貼簿！';
      }, function() {
        document.getElementById('msg').innerText = '複製失敗，請手動選取文字。';
      });
    }
  </script>
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
        weekday = ["一","二","三","四","五","六","日"][d.weekday()]
        label = f"{date_str}（{weekday}）"
        slots = []
        for slot in TIME_SLOTS:
            if not can_book_space(space_id, d):
                slots.append("🚫 不開放")
            else:
                st = get_slot_status(space_id, date_str, slot)
                slots.append(status_text(st))
        rows.append({
            "label": label,
            "weekend": d.weekday() >= 5,
            "slots": slots
        })

    return render_template_string(
        TEMPLATE,
        spaces=SPACES,
        space_id=space_id,
        today=today.isoformat(),
        end_date=end.isoformat(),
        rows=rows
    )

@app.route("/access-list")
def access_list():
    text = export_access_list_text(30)
    return render_template_string(ACCESS_TEMPLATE, access_text=text)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8502, debug=False)
