-- Family_dentists — повна схема бази даних v2.0

-- Лікарі
CREATE TABLE IF NOT EXISTS doctors (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT DEFAULT 'Стоматолог',
    telegram_id TEXT,
    color TEXT DEFAULT '#0ea5e9',
    active INTEGER DEFAULT 1
);

-- Пацієнти
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    telegram_id TEXT UNIQUE,
    full_name TEXT NOT NULL,
    phone TEXT,
    birthdate TEXT,
    address TEXT,
    notes TEXT,
    blood_type TEXT,
    allergies TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Записи на прийом
CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    doctor_id INTEGER REFERENCES doctors(id),
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    reminder_24h INTEGER DEFAULT 0,
    reminder_2h INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Електронна картка — медичні записи
CREATE TABLE IF NOT EXISTS medical_records (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    doctor_id INTEGER REFERENCES doctors(id),
    appointment_id INTEGER REFERENCES appointments(id),
    date TEXT NOT NULL,
    diagnosis TEXT,
    treatment TEXT,
    notes TEXT,
    next_visit TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Зубна формула
CREATE TABLE IF NOT EXISTS dental_chart (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id),
    tooth_number INTEGER NOT NULL,
    condition TEXT,
    treatment TEXT,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Фінанси
CREATE TABLE IF NOT EXISTS finances (
    id SERIAL PRIMARY KEY,
    appointment_id INTEGER REFERENCES appointments(id),
    patient_id INTEGER REFERENCES patients(id),
    doctor_id INTEGER REFERENCES doctors(id),
    amount REAL NOT NULL,
    type TEXT DEFAULT 'income',
    description TEXT,
    date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Послуги та ціни
CREATE TABLE IF NOT EXISTS services (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    category TEXT,
    duration_minutes INTEGER DEFAULT 30
);

-- FAQ
CREATE TABLE IF NOT EXISTS faq (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL,
    answer TEXT NOT NULL
);

-- Початкові дані
INSERT INTO doctors (name, specialty, color) VALUES
    ('Коваленко Олена Петрівна', 'Терапевт', '#0ea5e9'),
    ('Мельник Андрій Васильович', 'Хірург', '#10b981'),
    ('Бондар Ірина Миколаївна', 'Ортодонт', '#8b5cf6')
ON CONFLICT DO NOTHING;

INSERT INTO services (name, price, category, duration_minutes) VALUES
    ('Консультація', 200, 'Діагностика', 30),
    ('Лікування карієсу', 800, 'Терапія', 60),
    ('Видалення зуба', 600, 'Хірургія', 45),
    ('Чищення зубного каменю', 700, 'Гігієна', 60),
    ('Відбілювання', 1500, 'Естетика', 90),
    ('Коронка', 3500, 'Ортопедія', 60),
    ('Брекети (установка)', 8000, 'Ортодонтія', 120)
ON CONFLICT DO NOTHING;

INSERT INTO faq (keyword, answer) VALUES
    ('ціна', 'Консультація — від 200 грн. Детальніше про ціни: зателефонуйте нам або запишіться на прийом.'),
    ('адреса', '📍 Івано-Франківськ, вул. Незалежності 15. Режим роботи: Пн-Пт 9:00–19:00, Сб 9:00–14:00.'),
    ('режим', 'Ми працюємо: Пн-Пт 9:00–19:00, Субота 9:00–14:00, Неділя — вихідний.'),
    ('гарантія', 'На всі послуги надаємо гарантію згідно з договором.'),
    ('страховка', 'Працюємо з більшістю страхових компаній.')
ON CONFLICT DO NOTHING;
