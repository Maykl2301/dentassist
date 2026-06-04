import os
import asyncio
import threading
from dotenv import load_dotenv

load_dotenv()

# Ініціалізація PostgreSQL бази
import psycopg2
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
conn.autocommit = True
cur = conn.cursor()
with open("db/schema.sql", "r", encoding="utf-8") as f:
    cur.execute(f.read())
conn.close()
print('DB ready')

# Бот в окремому потоці
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from bot.bot import dp, bot, send_reminders
    async def start():
        asyncio.create_task(send_reminders())
        await dp.start_polling(bot)
    loop.run_until_complete(start())

t = threading.Thread(target=run_bot, daemon=True)
t.start()
print('Bot polling started')

from web.app import app
