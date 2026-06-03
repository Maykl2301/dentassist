#!/bin/bash
python -c "
import sqlite3
conn = sqlite3.connect('dentist.db')
conn.executescript(open('db/schema.sql').read())
conn.commit()
conn.close()
print('DB ready')
"
gunicorn web.app:app
