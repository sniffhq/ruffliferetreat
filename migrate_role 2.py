import sqlite3
conn = sqlite3.connect(r'C:\RuffLifeRetreat\instance\rufflife.db')
cur = conn.cursor()

cur.execute("PRAGMA table_info(user)")
cols = [row[1] for row in cur.fetchall()]
print('Tables/columns found:', cols)

if 'role' not in cols:
    cur.execute("ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'customer'")
    cur.execute("UPDATE user SET role = 'admin' WHERE is_admin = 1")
    conn.commit()
    print('Migration complete.')
else:
    print('role column already exists.')

cur.execute("SELECT role, COUNT(*) FROM user GROUP BY role")
for row in cur.fetchall():
    print(row)

conn.close()
