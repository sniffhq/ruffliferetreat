"""
One-time script: creates the blackout_date table.

Run on VPS with:
  python add_blackout_date.py
"""
import sqlite3, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB_CANDIDATES = [
    os.path.join(BASE, 'instance', 'rufflife.db'),
    os.path.join(BASE, 'instance', 'app.db'),
    os.path.join(BASE, 'rufflife.db'),
]

db_path = None
for p in DB_CANDIDATES:
    if os.path.exists(p):
        db_path = p
        break

if not db_path:
    sys.exit('ERROR: Could not find SQLite database.')

print(f'Using database: {db_path}')
conn = sqlite3.connect(db_path)
cur  = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blackout_date'")
if cur.fetchone():
    print('Table blackout_date already exists — nothing to do.')
else:
    cur.execute("""
        CREATE TABLE blackout_date (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date DATE    NOT NULL,
            end_date   DATE    NOT NULL,
            reason     VARCHAR(255),
            created_by VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    print('Created blackout_date table.')

conn.close()
print('Done.')
