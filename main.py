"""
Запускає Flask + Telegram бот в одному процесі
"""
import threading
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Ініціалізація бази
import sqlite3
conn = sqlite3.connect('dentist.db')
conn.executescript(open('db/schema.sql').read())
conn.commit()
conn.close()
print('DB ready')

# Запуск бота в окремому потоці
def run_bot():
    from bot.bot import main
    asyncio.run(main())

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()
print('Bot started')

# Запуск Flask
from web.app import app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
