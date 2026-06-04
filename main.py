import os
import asyncio
import threading
import time
from dotenv import load_dotenv

load_dotenv()

# База даних
try:
    import psycopg2
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    cur = conn.cursor()
    with open("db/schema.sql", "r", encoding="utf-8") as f:
        cur.execute(f.read())
    conn.close()
    print('DB ready')
except Exception as e:
    print(f'DB error: {e}')

# Бот
bot_loop = None
bot_ready = threading.Event()

def run_bot():
    global bot_loop
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    try:
        from bot.bot import dp, bot, send_reminders
        async def start():
            print('Bot polling starting...')
            asyncio.create_task(send_reminders())
            bot_ready.set()
            await dp.start_polling(bot)
        bot_loop.run_until_complete(start())
    except Exception as e:
        print(f'Bot error: {e}')
        import traceback
        traceback.print_exc()
        bot_ready.set()

t = threading.Thread(target=run_bot, daemon=True)
t.start()

# Чекаємо поки бот запуститься
bot_ready.wait(timeout=15)
print('Bot thread ready')

from web.app import app

if __name__ == '__main__':
    from waitress import serve
    port = int(os.getenv('PORT', 5000))
    print(f'Web starting on port {port}')
    serve(app, host='0.0.0.0', port=port)
