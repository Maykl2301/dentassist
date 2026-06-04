import os, asyncio
from dotenv import load_dotenv
load_dotenv()

try:
    import psycopg2
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(open("db/schema.sql").read())
    conn.close()
    print('DB ready')
except Exception as e:
    print(f'DB error: {e}')

webhook_url = os.getenv("WEBHOOK_URL","")
if webhook_url:
    from bot.bot import bot
    asyncio.run(bot.set_webhook(f"{webhook_url}/webhook", drop_pending_updates=True))
    print(f'Webhook: {webhook_url}/webhook')
else:
    print('No WEBHOOK_URL set!')

from web.app import app

if __name__ == '__main__':
    from waitress import serve
    port = int(os.getenv('PORT',5000))
    print(f'Starting on port {port}')
    serve(app, host='0.0.0.0', port=port)
