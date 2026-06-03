"""
Family_dentists — Веб-календар для адміністратора
Запуск: python web/app.py
Відкрити: http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import sqlite3
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dentist_secret_2024")
DB_PATH = os.getenv("DB_PATH", "dentist.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── Авторизація ──────────────────────────────────────────────

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Невірний пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ─── Головна сторінка (дашборд) ───────────────────────────────

@app.route("/")
@require_login
def dashboard():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()

    today_appointments = conn.execute("""
        SELECT a.id, a.time, a.status, a.reason,
               p.full_name, p.phone, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.date = ? AND a.status != 'cancelled'
        ORDER BY a.time
    """, (today,)).fetchall()

    stats = {
        "today": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE date = ? AND status != 'cancelled'", (today,)
        ).fetchone()[0],
        "week": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE date >= ? AND date <= ? AND status != 'cancelled'",
            (today, (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"))
        ).fetchone()[0],
        "patients": conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
        "done_today": conn.execute(
            "SELECT COUNT(*) FROM appointments WHERE date = ? AND status = 'done'", (today,)
        ).fetchone()[0],
    }
    conn.close()

    return render_template("dashboard.html",
        appointments=today_appointments,
        stats=stats,
        today=datetime.now().strftime("%d.%m.%Y"),
        today_raw=today
    )


# ─── Календар ─────────────────────────────────────────────────

@app.route("/calendar")
@require_login
def calendar():
    doctors = get_db().execute("SELECT * FROM doctors WHERE active = 1").fetchall()
    return render_template("calendar.html", doctors=doctors)

@app.route("/api/appointments")
@require_login
def api_appointments():
    start = request.args.get("start", "")[:10]
    end = request.args.get("end", "")[:10]
    conn = get_db()
    rows = conn.execute("""
        SELECT a.id, a.date, a.time, a.status, a.reason,
               p.full_name, d.name as doctor_name, d.id as doctor_id
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.date >= ? AND a.date <= ? AND a.status != 'cancelled'
        ORDER BY a.date, a.time
    """, (start, end)).fetchall()
    conn.close()

    colors = {1: "#4CAF50", 2: "#2196F3", 3: "#FF9800"}
    events = []
    for r in rows:
        events.append({
            "id": r["id"],
            "title": f"{r['time']} {r['full_name'].split()[0]} → {r['doctor_name'].split()[0]}",
            "start": f"{r['date']}T{r['time']}",
            "color": colors.get(r["doctor_id"], "#9C27B0"),
            "extendedProps": {
                "patient": r["full_name"],
                "doctor": r["doctor_name"],
                "reason": r["reason"],
                "status": r["status"]
            }
        })
    return jsonify(events)


# ─── API: управління записами ─────────────────────────────────

@app.route("/api/appointment/<int:appt_id>/status", methods=["POST"])
@require_login
def update_status(appt_id):
    status = request.json.get("status")
    if status not in ("confirmed", "done", "cancelled"):
        return jsonify({"error": "Невірний статус"}), 400
    conn = get_db()
    conn.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appt_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/appointment/new", methods=["POST"])
@require_login
def new_appointment():
    data = request.json
    conn = get_db()
    # Знаходимо або створюємо пацієнта
    patient = conn.execute(
        "SELECT id FROM patients WHERE phone = ?", (data["phone"],)
    ).fetchone()
    if not patient:
        conn.execute(
            "INSERT INTO patients (full_name, phone) VALUES (?, ?)",
            (data["full_name"], data["phone"])
        )
        patient_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        patient_id = patient["id"]
        conn.execute("UPDATE patients SET full_name = ? WHERE id = ?",
                     (data["full_name"], patient_id))

    conn.execute(
        "INSERT INTO appointments (patient_id, doctor_id, date, time, reason, status) VALUES (?,?,?,?,?,?)",
        (patient_id, data["doctor_id"], data["date"], data["time"],
         data.get("reason", ""), "confirmed")
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/patients")
@require_login
def api_patients():
    q = request.args.get("q", "")
    conn = get_db()
    patients = conn.execute(
        "SELECT id, full_name, phone FROM patients WHERE full_name LIKE ? OR phone LIKE ? LIMIT 10",
        (f"%{q}%", f"%{q}%")
    ).fetchall()
    conn.close()
    return jsonify([dict(p) for p in patients])


# ─── Пацієнти ─────────────────────────────────────────────────

@app.route("/patients")
@require_login
def patients():
    conn = get_db()
    patients = conn.execute("""
        SELECT p.*, COUNT(a.id) as visit_count,
               MAX(a.date) as last_visit
        FROM patients p
        LEFT JOIN appointments a ON p.id = a.patient_id AND a.status = 'done'
        GROUP BY p.id
        ORDER BY p.full_name
    """).fetchall()
    conn.close()
    return render_template("patients.html", patients=patients)

@app.route("/patient/<int:patient_id>")
@require_login
def patient_detail(patient_id):
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    history = conn.execute("""
        SELECT a.*, d.name as doctor_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ?
        ORDER BY a.date DESC, a.time DESC
    """, (patient_id,)).fetchall()
    conn.close()
    return render_template("patient_detail.html", patient=patient, history=history)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

@app.route('/webhook', methods=['POST'])
def webhook():
    import asyncio, json
    from flask import request
    from aiogram.types import Update
    async def process():
        from bot.bot import dp, bot
        data = request.get_json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    asyncio.run(process())
    return 'ok', 200
