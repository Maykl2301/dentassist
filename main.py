import threading
import asyncio
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# База даних
conn = sqlite3.connect('dentist.db')
conn.executescript(open('db/schema.sql').read())
conn.commit()
conn.close()
print('DB ready')

# Бот в окремому потоці
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from bot.bot import dp, bot, send_reminders, init_db
    async def start():
        init_db()
        asyncio.create_task(send_reminders())
        await dp.start_polling(bot)
    loop.run_until_complete(start())

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()
print('Bot started')

from web.app import app
