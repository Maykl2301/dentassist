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

from web.app import app

# Встановити webhook при старті
import asyncio
from bot.bot import bot, dp

async def set_webhook():
    webhook_url = os.getenv('WEBHOOK_URL', '')
    if webhook_url:
        await bot.set_webhook(f"{webhook_url}/webhook")
        print(f'Webhook set: {webhook_url}/webhook')

asyncio.run(set_webhook())
print('App ready')
