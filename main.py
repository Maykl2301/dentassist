import os
import sqlite3
import asyncio
from dotenv import load_dotenv

load_dotenv()

# База даних
conn = sqlite3.connect('dentist.db')
conn.executescript(open('db/schema.sql').read())
conn.commit()
conn.close()
print('DB ready')

async def main():
    from bot.bot import dp, bot, send_reminders, init_db
    from web.app import app
    import threading
    
    init_db()
    
    # Flask в окремому потоці
    port = int(os.getenv('PORT', 5000))
    def run_flask():
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    print(f'Web panel started on port {port}')
    
    # Бот в головному потоці
    asyncio.create_task(send_reminders())
    print('Starting bot polling...')
    await dp.start_polling(bot)

asyncio.run(main())
