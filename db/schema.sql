-- Family_dentists — схема бази даних
-- Виконати: sqlite3 dentist.db < schema.sql

-- Лікарі
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    specialty TEXT DEFAULT 'Стоматолог',
    telegram_id TEXT,
    active INTEGER DEFAULT 1
);

-- Пацієнти
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT UNIQUE,
    full_name TEXT NOT NULL,
    phone TEXT,
    birthdate TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- Записи на прийом
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER REFERENCES patients(id),
    doctor_id INTEGER REFERENCES doctors(id),
    date TEXT NOT NULL,          -- YYYY-MM-DD
    time TEXT NOT NULL,          -- HH:MM
    reason TEXT,
    status TEXT DEFAULT 'pending',  -- pending | confirmed | cancelled | done
    reminder_24h INTEGER DEFAULT 0, -- 0/1 чи надіслано нагадування
    reminder_2h INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- FAQ відповіді
CREATE TABLE IF NOT EXISTS faq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    answer TEXT NOT NULL
);

-- Вставляємо тестові дані
INSERT OR IGNORE INTO doctors (id, name, specialty) VALUES
    (1, 'Коваленко Олена Петрівна', 'Терапевт'),
    (2, 'Мельник Андрій Васильович', 'Хірург'),
    (3, 'Бондар Ірина Миколаївна', 'Ортодонт');

INSERT OR IGNORE INTO faq (keyword, answer) VALUES
    ('ціна', 'Консультація — від 200 грн. Детальніше про ціни: зателефонуйте нам або запишіться на прийом.'),
    ('адреса', '📍 Івано-Франківськ, вул. Незалежності 15. Режим роботи: Пн-Пт 9:00–19:00, Сб 9:00–14:00.'),
    ('режим', 'Ми працюємо: Пн-Пт 9:00–19:00, Субота 9:00–14:00, Неділя — вихідний.'),
    ('гарантія', 'На всі послуги надаємо гарантію згідно з договором. Деталі уточнюйте у лікаря.'),
    ('страховка', 'Працюємо з більшістю страхових компаній. Уточнюйте наявність вашого страховика.');
