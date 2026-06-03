"""
Family_dentists — Telegram бот для запису пацієнтів
Стек: aiogram 3.x + SQLite
Запуск: python bot.py
"""

import asyncio
import logging
import sqlite3
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
DB_PATH = os.getenv("DB_PATH", "dentist.db")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ─── База даних ────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with open("db/schema.sql", "r", encoding="utf-8") as f:
        script = f.read()
    conn = get_db()
    conn.executescript(script)
    conn.commit()
    conn.close()

def get_or_create_patient(telegram_id: str, full_name: str, phone: str = None):
    conn = get_db()
    patient = conn.execute(
        "SELECT * FROM patients WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    if not patient:
        conn.execute(
            "INSERT INTO patients (telegram_id, full_name, phone) VALUES (?, ?, ?)",
            (telegram_id, full_name, phone)
        )
        conn.commit()
        patient = conn.execute(
            "SELECT * FROM patients WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
    conn.close()
    return patient

def get_doctors():
    conn = get_db()
    doctors = conn.execute(
        "SELECT * FROM doctors WHERE active = 1"
    ).fetchall()
    conn.close()
    return doctors

def get_available_times(date: str, doctor_id: int):
    """Повертає список вільних часових слотів"""
    all_slots = [
        "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "14:00", "14:30", "15:00", "15:30",
        "16:00", "16:30", "17:00", "17:30", "18:00", "18:30"
    ]
    conn = get_db()
    booked = [row[0] for row in conn.execute(
        "SELECT time FROM appointments WHERE date = ? AND doctor_id = ? AND status != 'cancelled'",
        (date, doctor_id)
    ).fetchall()]
    conn.close()
    return [t for t in all_slots if t not in booked]

def save_appointment(patient_id: int, doctor_id: int, date: str, time: str, reason: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO appointments (patient_id, doctor_id, date, time, reason) VALUES (?,?,?,?,?)",
        (patient_id, doctor_id, date, time, reason)
    )
    conn.commit()
    conn.close()

def get_patient_appointments(telegram_id: str):
    conn = get_db()
    rows = conn.execute("""
        SELECT a.id, a.date, a.time, a.reason, a.status, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE p.telegram_id = ?
          AND a.date >= date('now', 'localtime')
          AND a.status != 'cancelled'
        ORDER BY a.date, a.time
    """, (telegram_id,)).fetchall()
    conn.close()
    return rows

def cancel_appointment(appointment_id: int, telegram_id: str):
    conn = get_db()
    conn.execute("""
        UPDATE appointments SET status = 'cancelled'
        WHERE id = ? AND patient_id = (
            SELECT id FROM patients WHERE telegram_id = ?
        )
    """, (appointment_id, telegram_id))
    conn.commit()
    conn.close()

def get_faq_answer(text: str):
    conn = get_db()
    rows = conn.execute("SELECT keyword, answer FROM faq").fetchall()
    conn.close()
    text_lower = text.lower()
    for row in rows:
        if row["keyword"] in text_lower:
            return row["answer"]
    return None

# ─── FSM стани ────────────────────────────────────────────────

class BookingState(StatesGroup):
    choosing_doctor = State()
    choosing_date = State()
    choosing_time = State()
    entering_reason = State()
    entering_phone = State()
    confirming = State()


# ─── Клавіатури ───────────────────────────────────────────────

def main_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📅 Записатися"), KeyboardButton(text="📋 Мої записи")],
        [KeyboardButton(text="❌ Скасувати запис"), KeyboardButton(text="❓ Запитання")],
        [KeyboardButton(text="📞 Контакти")]
    ], resize_keyboard=True)

def doctors_kb(doctors):
    buttons = [
        [InlineKeyboardButton(text=f"👨‍⚕️ {d['name']}", callback_data=f"doc_{d['id']}")]
        for d in doctors
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def dates_kb():
    today = datetime.now()
    buttons = []
    row = []
    for i in range(1, 8):
        d = today + timedelta(days=i)
        if d.weekday() < 6:  # Пн-Сб
            label = d.strftime("%d.%m (%a)").replace(
                "Mon", "Пн").replace("Tue", "Вт").replace("Wed", "Ср").replace(
                "Thu", "Чт").replace("Fri", "Пт").replace("Sat", "Сб")
            row.append(InlineKeyboardButton(
                text=label, callback_data=f"date_{d.strftime('%Y-%m-%d')}"
            ))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def times_kb(slots):
    buttons = []
    row = []
    for t in slots:
        row.append(InlineKeyboardButton(text=t, callback_data=f"time_{t}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def appointments_kb(appointments):
    buttons = [
        [InlineKeyboardButton(
            text=f"❌ Скасувати {a['date']} {a['time']}",
            callback_data=f"cancel_{a['id']}"
        )]
        for a in appointments
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm_yes"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm_no")
    ]])


# ─── Обробники: старт ─────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Вітаємо в стоматології *Family Dentists*!\n\n"
        f"Тут ви можете:\n"
        f"• 📅 Записатися на прийом\n"
        f"• 📋 Переглянути свої записи\n"
        f"• ❌ Скасувати запис\n"
        f"• ❓ Отримати відповіді на питання\n\n"
        f"Оберіть дію нижче 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )


# ─── Запис на прийом ──────────────────────────────────────────

@dp.message(F.text == "📅 Записатися")
async def start_booking(message: Message, state: FSMContext):
    doctors = get_doctors()
    await state.set_state(BookingState.choosing_doctor)
    await message.answer(
        "👨‍⚕️ Оберіть лікаря:",
        reply_markup=doctors_kb(doctors)
    )

@dp.callback_query(BookingState.choosing_doctor, F.data.startswith("doc_"))
async def choose_doctor(callback: CallbackQuery, state: FSMContext):
    doctor_id = int(callback.data.split("_")[1])
    conn = get_db()
    doctor = conn.execute("SELECT * FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
    conn.close()
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor["name"])
    await state.set_state(BookingState.choosing_date)
    await callback.message.edit_text(
        f"✅ Лікар: *{doctor['name']}*\n\n📅 Оберіть зручну дату:",
        parse_mode="Markdown",
        reply_markup=dates_kb()
    )

@dp.callback_query(BookingState.choosing_date, F.data.startswith("date_"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    date = callback.data.split("_")[1]
    data = await state.get_data()
    slots = get_available_times(date, data["doctor_id"])
    if not slots:
        await callback.answer("😔 На цю дату немає вільних місць", show_alert=True)
        return
    await state.update_data(date=date)
    await state.set_state(BookingState.choosing_time)
    formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"📅 Дата: *{formatted}*\n\n🕐 Оберіть час:",
        parse_mode="Markdown",
        reply_markup=times_kb(slots)
    )

@dp.callback_query(BookingState.choosing_time, F.data.startswith("time_"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    time = callback.data.split("_")[1]
    await state.update_data(time=time)
    await state.set_state(BookingState.entering_reason)
    await callback.message.edit_text(
        f"🕐 Час: *{time}*\n\n💬 Опишіть причину візиту (або натисніть /skip):",
        parse_mode="Markdown"
    )

@dp.message(BookingState.entering_reason)
async def enter_reason(message: Message, state: FSMContext):
    reason = message.text if message.text != "/skip" else "Не вказано"
    await state.update_data(reason=reason)
    data = await state.get_data()

    # Перевіряємо чи є телефон
    conn = get_db()
    patient = conn.execute(
        "SELECT phone FROM patients WHERE telegram_id = ?",
        (str(message.from_user.id),)
    ).fetchone()
    conn.close()

    if patient and patient["phone"]:
        await state.set_state(BookingState.confirming)
        formatted_date = datetime.strptime(data["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
        await message.answer(
            f"📋 *Підтвердіть запис:*\n\n"
            f"👨‍⚕️ Лікар: {data['doctor_name']}\n"
            f"📅 Дата: {formatted_date}\n"
            f"🕐 Час: {data['time']}\n"
            f"💬 Причина: {data['reason']}",
            parse_mode="Markdown",
            reply_markup=confirm_kb()
        )
    else:
        await state.set_state(BookingState.entering_phone)
        await message.answer("📞 Введіть ваш номер телефону (наприклад: +380991234567):")

@dp.message(BookingState.entering_phone)
async def enter_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    await state.set_state(BookingState.confirming)
    formatted_date = datetime.strptime(data["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    await message.answer(
        f"📋 *Підтвердіть запис:*\n\n"
        f"👨‍⚕️ Лікар: {data['doctor_name']}\n"
        f"📅 Дата: {formatted_date}\n"
        f"🕐 Час: {data['time']}\n"
        f"📞 Телефон: {phone}\n"
        f"💬 Причина: {data['reason']}",
        parse_mode="Markdown",
        reply_markup=confirm_kb()
    )

@dp.callback_query(BookingState.confirming, F.data == "confirm_yes")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = callback.from_user
    phone = data.get("phone")

    patient = get_or_create_patient(
        str(user.id),
        user.full_name or user.username or "Пацієнт",
        phone
    )
    if phone:
        conn = get_db()
        conn.execute("UPDATE patients SET phone = ? WHERE id = ?", (phone, patient["id"]))
        conn.commit()
        conn.close()

    save_appointment(patient["id"], data["doctor_id"], data["date"], data["time"], data["reason"])

    formatted_date = datetime.strptime(data["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"✅ *Запис підтверджено!*\n\n"
        f"👨‍⚕️ {data['doctor_name']}\n"
        f"📅 {formatted_date} о {data['time']}\n\n"
        f"Ми нагадаємо вам за 24 год і за 2 год до прийому.\n"
        f"📍 Адреса: вул. Незалежності 15, Івано-Франківськ",
        parse_mode="Markdown"
    )

    # Повідомлення адміну з кнопками підтвердження
    conn2 = get_db()
    appt = conn2.execute("SELECT id FROM appointments WHERE patient_id=? ORDER BY id DESC LIMIT 1", (patient["id"],)).fetchone()
    conn2.close()
    appt_id = appt["id"] if appt else 0
    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"adm_confirm_{appt_id}"),
                InlineKeyboardButton(text="❌ Відхилити", callback_data=f"adm_cancel_{appt_id}")
            ]])
            await bot.send_message(
                admin_id,
                f"🆕 *Новий запис!*\n"
                f"👤 {user.full_name} (@{user.username})\n"
                f"👨‍⚕️ {data['doctor_name']}\n"
                f"📅 {formatted_date} о {data['time']}\n"
                f"💬 {data['reason']}\n\n"
                f"Підтвердіть або відхиліть запис:",
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception:
            pass

    await state.clear()
    await callback.message.answer("Головне меню:", reply_markup=main_menu_kb())

@dp.callback_query(BookingState.confirming, F.data == "confirm_no")
async def cancel_booking_form(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Запис скасовано.")
    await callback.message.answer("Головне меню:", reply_markup=main_menu_kb())


# ─── Мої записи ───────────────────────────────────────────────

@dp.message(F.text == "📋 Мої записи")
async def my_appointments(message: Message):
    appointments = get_patient_appointments(str(message.from_user.id))
    if not appointments:
        await message.answer(
            "У вас немає майбутніх записів.\n\nЗапишіться через кнопку 📅 Записатися",
            reply_markup=main_menu_kb()
        )
        return

    text = "📋 *Ваші майбутні записи:*\n\n"
    for a in appointments:
        d = datetime.strptime(a["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
        status_emoji = {"pending": "🟡", "confirmed": "✅", "done": "✔️"}.get(a["status"], "🔵")
        text += f"{status_emoji} {d} о {a['time']}\n"
        text += f"   👨‍⚕️ {a['doctor_name']}\n"
        text += f"   💬 {a['reason'] or 'Без опису'}\n\n"

    await message.answer(text, parse_mode="Markdown", reply_markup=main_menu_kb())


# ─── Скасування ───────────────────────────────────────────────

@dp.message(F.text == "❌ Скасувати запис")
async def cancel_appointment_start(message: Message):
    appointments = get_patient_appointments(str(message.from_user.id))
    if not appointments:
        await message.answer("У вас немає активних записів.", reply_markup=main_menu_kb())
        return

    kb = appointments_kb(appointments)
    await message.answer("Оберіть запис для скасування:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cancel_"))
async def process_cancel(callback: CallbackQuery):
    appt_id = int(callback.data.split("_")[1])
    cancel_appointment(appt_id, str(callback.from_user.id))
    await callback.message.edit_text("✅ Запис скасовано. Будемо раді бачити вас знову!")
    await callback.message.answer("Головне меню:", reply_markup=main_menu_kb())


# ─── FAQ та контакти ──────────────────────────────────────────

@dp.message(F.text == "❓ Запитання")
async def faq_start(message: Message):
    await message.answer(
        "❓ *Часті запитання:*\n\n"
        "Напишіть ваше питання або оберіть з популярних:\n\n"
        "• Ціна / вартість лікування\n"
        "• Адреса та режим роботи\n"
        "• Гарантія на послуги\n"
        "• Страховка\n\n"
        "Або надішліть будь-яке питання — я відповім 🙂",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📞 Контакти")
async def contacts(message: Message):
    await message.answer(
        "📍 *Family Dentists*\n\n"
        "📌 Адреса: вул. Незалежності 15, Івано-Франківськ\n"
        "📞 Телефон: +380 XX XXX-XX-XX\n"
        "🕐 Графік: Пн-Пт 9:00–19:00, Сб 9:00–14:00\n"
        "💬 Telegram: @family_dentists_bot\n\n"
        "📅 Запис онлайн — просто натисніть 📅 Записатися",
        parse_mode="Markdown"
    )


# ─── Адмін команди ────────────────────────────────────────────

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ заборонено.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    appointments = conn.execute("""
        SELECT a.time, p.full_name, p.phone, d.name as doctor_name, a.status, a.reason, a.id
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.date = ? AND a.status != 'cancelled'
        ORDER BY a.time
    """, (today,)).fetchall()
    conn.close()

    if not appointments:
        await message.answer("📋 На сьогодні записів немає.")
        return

    text = f"📋 *Записи на сьогодні ({datetime.now().strftime('%d.%m.%Y')}):*\n\n"
    for a in appointments:
        status_emoji = {"pending": "🟡", "confirmed": "✅", "done": "✔️"}.get(a["status"], "🔵")
        text += f"{status_emoji} *{a['time']}* — {a['full_name']}\n"
        text += f"   👨‍⚕️ {a['doctor_name']}\n"
        if a["phone"]:
            text += f"   📞 {a['phone']}\n"
        text += f"   💬 {a['reason'] or '—'}\n\n"

    buttons = []
    for a in appointments:
        buttons.append([
            InlineKeyboardButton(
                text=f"✔️ Завершити {a['time']} {a['full_name'].split()[0]}",
                callback_data=f"done_{a['id']}"
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data.startswith("done_"))
async def mark_done(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ заборонено")
        return
    appt_id = int(callback.data.split("_")[1])
    conn = get_db()
    conn.execute("UPDATE appointments SET status = 'done' WHERE id = ?", (appt_id,))
    conn.commit()
    conn.close()
    await callback.answer("✅ Прийом завершено!")

@dp.message(Command("stats"))
async def admin_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    month_start = datetime.now().strftime("%Y-%m-01")

    today_count = conn.execute(
        "SELECT COUNT(*) FROM appointments WHERE date = ? AND status != 'cancelled'", (today,)
    ).fetchone()[0]
    month_count = conn.execute(
        "SELECT COUNT(*) FROM appointments WHERE date >= ? AND status != 'cancelled'", (month_start,)
    ).fetchone()[0]
    total_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    conn.close()

    await message.answer(
        f"📊 *Статистика:*\n\n"
        f"📅 Сьогодні записів: *{today_count}*\n"
        f"📆 Цього місяця: *{month_count}*\n"
        f"👥 Всього пацієнтів: *{total_patients}*",
        parse_mode="Markdown"
    )


# ─── Текстовий FAQ (вільний текст) ────────────────────────────

@dp.message()
async def handle_text(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return

    answer = get_faq_answer(message.text)
    if answer:
        await message.answer(answer)
    else:
        await message.answer(
            "Вибачте, я не розумію це питання 🤔\n\n"
            "Оберіть дію з меню або напишіть:\n"
            "• *ціна* — вартість послуг\n"
            "• *адреса* — як нас знайти\n"
            "• *режим* — години роботи",
            parse_mode="Markdown",
            reply_markup=main_menu_kb()
        )


# ─── Система нагадувань ───────────────────────────────────────

async def send_reminders():
    """Запускається кожні 30 хвилин. Надсилає нагадування за 24 год і 2 год."""
    while True:
        try:
            now = datetime.now()
            in_24h = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
            in_2h = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")

            conn = get_db()

            # Нагадування за 24 години
            rows_24 = conn.execute("""
                SELECT a.id, a.time, a.date, p.telegram_id, p.full_name, d.name as doctor_name
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.reminder_24h = 0 AND a.status = 'pending'
                  AND datetime(a.date || ' ' || a.time) BETWEEN ? AND ?
            """, (
                (now + timedelta(hours=23, minutes=30)).strftime("%Y-%m-%d %H:%M"),
                (now + timedelta(hours=24, minutes=30)).strftime("%Y-%m-%d %H:%M")
            )).fetchall()

            for r in rows_24:
                if r["telegram_id"]:
                    try:
                        d = datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
                        await bot.send_message(
                            r["telegram_id"],
                            f"🔔 *Нагадування!*\n\n"
                            f"Завтра о *{r['time']}* у вас прийом:\n"
                            f"👨‍⚕️ {r['doctor_name']}\n"
                            f"📅 {d}\n\n"
                            f"📍 Family Dentists, вул. Незалежності 15\n\n"
                            f"Якщо не зможете прийти — скасуйте запис у боті 🙏",
                            parse_mode="Markdown"
                        )
                        conn.execute("UPDATE appointments SET reminder_24h = 1 WHERE id = ?", (r["id"],))
                    except Exception as e:
                        logging.warning(f"Не вдалося надіслати нагадування: {e}")

            # Нагадування за 2 години
            rows_2 = conn.execute("""
                SELECT a.id, a.time, a.date, p.telegram_id, d.name as doctor_name
                FROM appointments a
                JOIN patients p ON a.patient_id = p.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.reminder_2h = 0 AND a.status IN ('pending', 'confirmed')
                  AND datetime(a.date || ' ' || a.time) BETWEEN ? AND ?
            """, (
                (now + timedelta(hours=1, minutes=45)).strftime("%Y-%m-%d %H:%M"),
                (now + timedelta(hours=2, minutes=15)).strftime("%Y-%m-%d %H:%M")
            )).fetchall()

            for r in rows_2:
                if r["telegram_id"]:
                    try:
                        await bot.send_message(
                            r["telegram_id"],
                            f"⏰ *Нагадування за 2 години!*\n\n"
                            f"Сьогодні о *{r['time']}* у вас прийом до {r['doctor_name']}.\n\n"
                            f"Чекаємо вас! 🦷",
                            parse_mode="Markdown"
                        )
                        conn.execute("UPDATE appointments SET reminder_2h = 1 WHERE id = ?", (r["id"],))
                    except Exception as e:
                        logging.warning(f"Не вдалося надіслати нагадування: {e}")

            conn.commit()
            conn.close()

        except Exception as e:
            logging.error(f"Помилка нагадувань: {e}")

        await asyncio.sleep(1800)  # 30 хвилин


# ─── Запуск ───────────────────────────────────────────────────


@dp.callback_query(F.data.startswith("adm_confirm_"))
async def admin_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ заборонено")
        return
    appt_id = int(callback.data.split("_")[2])
    conn = get_db()
    appt = conn.execute("""
        SELECT a.*, p.telegram_id, p.full_name, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.id = ?
    """, (appt_id,)).fetchone()
    conn.execute("UPDATE appointments SET status='confirmed' WHERE id=?", (appt_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ *Підтверджено!*",
        parse_mode="Markdown"
    )
    if appt and appt["telegram_id"]:
        d = datetime.strptime(appt["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
        try:
            await bot.send_message(
                appt["telegram_id"],
                f"✅ *Ваш запис підтверджено!*\n\n"
                f"👨\u200d⚕️ {appt['doctor_name']}\n"
                f"📅 {d} о {appt['time']}\n\n"
                f"Чекаємо вас! 🦷",
                parse_mode="Markdown"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("adm_cancel_"))
async def admin_cancel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ заборонено")
        return
    appt_id = int(callback.data.split("_")[2])
    conn = get_db()
    appt = conn.execute("""
        SELECT a.*, p.telegram_id, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.id = ?
    """, (appt_id,)).fetchone()
    conn.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appt_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ *Відхилено*",
        parse_mode="Markdown"
    )
    if appt and appt["telegram_id"]:
        try:
            await bot.send_message(
                appt["telegram_id"],
                f"😔 На жаль, ваш запис відхилено.\n\n"
                f"Спробуйте обрати інший час через 📅 Записатися"
            )
        except Exception:
            pass


@dp.callback_query(F.data.startswith("adm_confirm_"))
async def admin_confirm(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ заборонено")
        return
    appt_id = int(callback.data.split("_")[2])
    conn = get_db()
    appt = conn.execute("""
        SELECT a.*, p.telegram_id, p.full_name, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.id = ?
    """, (appt_id,)).fetchone()
    conn.execute("UPDATE appointments SET status='confirmed' WHERE id=?", (appt_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ *Підтверджено!*",
        parse_mode="Markdown"
    )
    if appt and appt["telegram_id"]:
        d = datetime.strptime(appt["date"], "%Y-%m-%d").strftime("%d.%m.%Y")
        try:
            await bot.send_message(
                appt["telegram_id"],
                f"✅ *Ваш запис підтверджено!*\n\n"
                f"👨\u200d⚕️ {appt['doctor_name']}\n"
                f"📅 {d} о {appt['time']}\n\n"
                f"Чекаємо вас! 🦷",
                parse_mode="Markdown"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("adm_cancel_"))
async def admin_cancel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ заборонено")
        return
    appt_id = int(callback.data.split("_")[2])
    conn = get_db()
    appt = conn.execute("""
        SELECT a.*, p.telegram_id, d.name as doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.id = ?
    """, (appt_id,)).fetchone()
    conn.execute("UPDATE appointments SET status='cancelled' WHERE id=?", (appt_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ *Відхилено*",
        parse_mode="Markdown"
    )
    if appt and appt["telegram_id"]:
        try:
            await bot.send_message(
                appt["telegram_id"],
                f"😔 На жаль, ваш запис відхилено.\n\n"
                f"Спробуйте обрати інший час через 📅 Записатися"
            )
        except Exception:
            pass

async def main():
    init_db()
    webhook_url = os.getenv("WEBHOOK_URL", "")
    if webhook_url:
        from aiohttp import web
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        asyncio.create_task(send_reminders())
        await bot.set_webhook(f"{webhook_url}/webhook")
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
        setup_application(app, dp, bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        await asyncio.Event().wait()
    else:
        asyncio.create_task(send_reminders())
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
