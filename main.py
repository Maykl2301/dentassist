import os
import sqlite3
import asyncio
import threading
from dotenv import load_dotenv

load_dotenv()

# База даних
conn = sqlite3.connect('dentist.db')
conn.executescript(open('db/schema.sql').read())
conn.commit()
conn.close()

# Глобальний event loop для бота
bot_loop = asyncio.new_event_loop()

def start_bot_loop():
    asyncio.set_event_loop(bot_loop)
    from bot.bot import dp, bot, send_reminders, init_db
    async def run():
        init_db()
        asyncio.create_task(send_reminders())
        await dp.start_polling(bot)
    bot_loop.run_until_complete(run())

# Запускаємо бота в окремому потоці
t = threading.Thread(target=start_bot_loop, daemon=True)
t.start()
print('Bot polling started')

from web.app import app
