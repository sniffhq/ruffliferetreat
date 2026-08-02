"""
Archive confirmed bot accounts.
Run from C:\\RuffLifeRetreat:  python archive_bots.py
"""
import sqlite3, os, sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'rufflife.db')
if not os.path.exists(DB_PATH):
    print(f'ERROR: Database not found at {DB_PATH}')
    sys.exit(1)

# Known bot phone numbers found via Twilio failures
BOT_PHONES = [
    '2828356297',
    '2929739399',
]

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
archived = 0

for phone in BOT_PHONES:
    rows = cur.execute(
        "SELECT id, first_name, last_name, email FROM user WHERE phone=? AND is_active=1",
        (phone,)
    ).fetchall()
    for uid, fn, ln, email in rows:
        print(f'Archiving [{uid}] {fn} {ln} <{email}> phone={phone}')
        cur.execute(
            "UPDATE user SET is_active=0, archived_at=? WHERE id=?",
            (now, uid)
        )
        archived += 1

conn.commit()
conn.close()
print(f'\nDone. {archived} account(s) archived.')
