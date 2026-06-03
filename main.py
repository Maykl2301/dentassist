import threading
import asyncio
import os
import sqlite3

# База даних
conn = sqlite3.connect('dentist.db')
conn.executescript(open('db/schema.sql').read())
conn.commit()
conn.close()
print('DB ready')

# Бот в окремому потоці з власним event loop
def run_bot():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    os.environ.setdefault('BOT_TOKEN', os.getenv('BOT_TOKEN', ''))
    
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    
    # Імпортуємо dp та bot з bot.py
    import sys
    sys.path.insert(0, '.')
    
    from bot.bot import dp, bot, send_reminders
    
    async def start():
        asyncio.create_task(send_reminders())
        await dp.start_polling(bot)
    
    loop.run_until_complete(start())

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()
print('Bot thread started')

from web.app import app
