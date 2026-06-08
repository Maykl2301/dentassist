"""
Family_dentists — Веб-панель v2.0
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dentist_secret_2024")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DATABASE_URL = os.getenv("DATABASE_URL")


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    with open("db/schema.sql", "r", encoding="utf-8") as f:
        cur.execute(f.read())
    conn.close()
    print("DB ready")


# ── Авторизація ──────────────────────────────────────────────

def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


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


# ── Дашборд ──────────────────────────────────────────────────

@app.route("/")
@require_login
def dashboard():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT a.id, a.time, a.status, a.reason,
               p.full_name, p.phone, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.date = %s AND a.status != 'cancelled'
        ORDER BY a.time
    """, (today,))
    appointments = cur.fetchall()

    cur.execute("SELECT COUNT(*) as c FROM appointments WHERE date = %s AND status != 'cancelled'", (today,))
    today_count = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) as c FROM appointments WHERE date = %s AND status = 'done'", (today,))
    done_count = cur.fetchone()['c']

    week_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) as c FROM appointments WHERE date >= %s AND date <= %s AND status != 'cancelled'", (today, week_end))
    week_count = cur.fetchone()['c']

    cur.execute("SELECT COUNT(*) as c FROM patients")
    patients_count = cur.fetchone()['c']

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM finances WHERE date = %s AND type = 'income'
    """, (today,))
    today_income = cur.fetchone()['total']

    conn.close()

    stats = {
        'today': today_count,
        'done_today': done_count,
        'week': week_count,
        'patients': patients_count,
        'today_income': today_income
    }

    return render_template("dashboard.html",
        appointments=appointments,
        stats=stats,
        today=datetime.now().strftime("%d.%m.%Y"),
        today_raw=today
    )


# ── Календар ─────────────────────────────────────────────────

@app.route("/calendar")
@require_login
def calendar():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM doctors WHERE active = 1")
    doctors = cur.fetchall()
    conn.close()
    return render_template("calendar.html", doctors=doctors)


@app.route("/api/appointments")
@require_login
def api_appointments():
    start = request.args.get("start", "")[:10]
    end = request.args.get("end", "")[:10]
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT a.id, a.date, a.time, a.status, a.reason,
               p.full_name, d.name as doctor_name, d.id as doctor_id, d.color
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.date >= %s AND a.date <= %s AND a.status != 'cancelled'
        ORDER BY a.date, a.time
    """, (start, end))
    rows = cur.fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append({
            "id": r["id"],
            "title": f"{r['time']} {r['full_name'].split()[0]}",
            "start": f"{r['date']}T{r['time']}",
            "color": r["color"] or "#0ea5e9",
            "extendedProps": {
                "patient": r["full_name"],
                "doctor": r["doctor_name"],
                "reason": r["reason"],
                "status": r["status"]
            }
        })
    return jsonify(events)


@app.route("/api/appointment/new", methods=["POST"])
@require_login
def new_appointment():
    data = request.json
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM patients WHERE phone = %s", (data["phone"],))
    patient = cur.fetchone()

    if not patient:
        cur.execute(
            "INSERT INTO patients (full_name, phone) VALUES (%s, %s) RETURNING id",
            (data["full_name"], data["phone"])
        )
        patient_id = cur.fetchone()['id']
    else:
        patient_id = patient["id"]
        cur.execute("UPDATE patients SET full_name = %s WHERE id = %s", (data["full_name"], patient_id))

    cur.execute(
        "INSERT INTO appointments (patient_id, doctor_id, date, time, reason, status) VALUES (%s,%s,%s,%s,%s,'confirmed')",
        (patient_id, data["doctor_id"], data["date"], data["time"], data.get("reason", ""))
    )
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/appointment/<int:appt_id>/status", methods=["POST"])
@require_login
def update_status(appt_id):
    status = request.json.get("status")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE appointments SET status = %s WHERE id = %s", (status, appt_id))
    conn.close()
    return jsonify({"ok": True})


# ── Пацієнти ─────────────────────────────────────────────────

@app.route("/patients")
@require_login
def patients():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT p.*,
               COUNT(a.id) as visit_count,
               MAX(a.date) as last_visit
        FROM patients p
        LEFT JOIN appointments a ON p.id = a.patient_id AND a.status = 'done'
        GROUP BY p.id
        ORDER BY p.full_name
    """)
    patients = cur.fetchall()
    conn.close()
    return render_template("patients.html", patients=patients)


@app.route("/patient/<int:patient_id>")
@require_login
def patient_detail(patient_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM patients WHERE id = %s", (patient_id,))
    patient = cur.fetchone()

    cur.execute("""
        SELECT a.*, d.name as doctor_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = %s
        ORDER BY a.date DESC, a.time DESC
    """, (patient_id,))
    history = cur.fetchall()

    cur.execute("""
        SELECT mr.*, d.name as doctor_name
        FROM medical_records mr
        JOIN doctors d ON mr.doctor_id = d.id
        WHERE mr.patient_id = %s
        ORDER BY mr.date DESC
    """, (patient_id,))
    records = cur.fetchall()

    cur.execute("""
        SELECT * FROM dental_chart
        WHERE patient_id = %s
    """, (patient_id,))
    dental_rows = cur.fetchall()
    dental_chart = {str(r['tooth_number']): r for r in dental_rows}

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM finances WHERE patient_id = %s AND type = 'income'
    """, (patient_id,))
    total_paid = cur.fetchone()['total']

    conn.close()
    return render_template("patient_detail.html",
        patient=patient,
        history=history,
        records=records,
        dental_chart=dental_chart,
        total_paid=total_paid
    )


@app.route("/api/medical_record/new", methods=["POST"])
@require_login
def new_medical_record():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO medical_records (patient_id, doctor_id, appointment_id, date, diagnosis, treatment, notes, next_visit)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data['patient_id'], data['doctor_id'],
        data.get('appointment_id'), data['date'],
        data['diagnosis'], data['treatment'],
        data.get('notes', ''), data.get('next_visit', '')
    ))
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/dental_chart/update", methods=["POST"])
@require_login
def update_dental_chart():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO dental_chart (patient_id, tooth_number, condition, treatment, notes)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (patient_id, tooth_number)
        DO UPDATE SET condition = %s, treatment = %s, notes = %s, updated_at = NOW()
    """, (
        data['patient_id'], data['tooth_number'],
        data['condition'], data['treatment'], data.get('notes', ''),
        data['condition'], data['treatment'], data.get('notes', '')
    ))
    conn.close()
    return jsonify({"ok": True})


# ── Фінанси ──────────────────────────────────────────────────

@app.route("/finances")
@require_login
def finances():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    month_start = datetime.now().strftime("%Y-%m-01")
    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("""
        SELECT f.*, p.full_name as patient_name, d.name as doctor_name
        FROM finances f
        LEFT JOIN patients p ON f.patient_id = p.id
        LEFT JOIN doctors d ON f.doctor_id = d.id
        WHERE f.date >= %s
        ORDER BY f.date DESC, f.id DESC
    """, (month_start,))
    transactions = cur.fetchall()

    cur.execute("SELECT COALESCE(SUM(amount),0) as t FROM finances WHERE type='income' AND date >= %s", (month_start,))
    month_income = cur.fetchone()['t']

    cur.execute("SELECT COALESCE(SUM(amount),0) as t FROM finances WHERE type='income' AND date = %s", (today,))
    today_income = cur.fetchone()['t']

    cur.execute("SELECT * FROM services ORDER BY category, name")
    services = cur.fetchall()

    conn.close()
    return render_template("finances.html",
        transactions=transactions,
        month_income=month_income,
        today_income=today_income,
        services=services
    )


@app.route("/api/finance/add", methods=["POST"])
@require_login
def add_finance():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO finances (patient_id, doctor_id, appointment_id, amount, type, description, date)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        data.get('patient_id'), data.get('doctor_id'),
        data.get('appointment_id'), data['amount'],
        data.get('type', 'income'), data.get('description', ''),
        data.get('date', datetime.now().strftime("%Y-%m-%d"))
    ))
    conn.close()
    return jsonify({"ok": True})


# ── Аналітика ────────────────────────────────────────────────

@app.route("/analytics")
@require_login
def analytics():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT TO_CHAR(date::date, 'YYYY-MM') as month,
               SUM(amount) as total
        FROM finances WHERE type = 'income'
        GROUP BY month ORDER BY month DESC LIMIT 6
    """)
    monthly = cur.fetchall()

    cur.execute("""
        SELECT d.name, COUNT(a.id) as count
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.status = 'done'
        GROUP BY d.name ORDER BY count DESC
    """)
    by_doctor = cur.fetchall()

    cur.execute("SELECT COUNT(*) as c FROM patients")
    total_patients = cur.fetchone()['c']

    cur.execute("""
        SELECT COUNT(*) as c FROM patients
        WHERE created_at >= NOW() - INTERVAL '30 days'
    """)
    new_patients = cur.fetchone()['c']

    conn.close()
    return render_template("analytics.html",
        monthly=monthly,
        by_doctor=by_doctor,
        total_patients=total_patients,
        new_patients=new_patients
    )


# ── API для пацієнтів ────────────────────────────────────────

@app.route("/api/patients")
@require_login
def api_patients():
    q = request.args.get("q", "")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, full_name, phone FROM patients WHERE full_name ILIKE %s OR phone LIKE %s LIMIT 10",
        (f"%{q}%", f"%{q}%")
    )
    patients = cur.fetchall()
    conn.close()
    return jsonify([dict(p) for p in patients])


@app.route("/api/doctors")
@require_login
def api_doctors():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM doctors WHERE active = 1")
    doctors = cur.fetchall()
    conn.close()
    return jsonify([dict(d) for d in doctors])


# ── Webhook ──────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    import asyncio
    from aiogram.types import Update
    data = request.get_json(force=True, silent=True)
    if not data:
        return 'ok', 200
    async def process():
        from bot.bot import dp, bot
        try:
            update = Update.model_validate(data, context={"bot": bot})
            await dp.feed_update(bot, update)
        except Exception as e:
            print(f"Webhook error: {e}")
    asyncio.run(process())
    return 'ok', 200


if __name__ == '__main__':
    from waitress import serve
    port = int(os.getenv('PORT', 5000))
    serve(app, host='0.0.0.0', port=port)
