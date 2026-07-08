"""
Migration: add sunday (and saturday to waitlist) columns for all-week daycare.
Run once on VPS: python add_daycare_sunday.py
"""
import sqlite3, os

db_path = os.path.join('instance', 'rufflife.db')
con = sqlite3.connect(db_path)
cur = con.cursor()

existing = {row[1] for row in cur.execute("PRAGMA table_info(daycare_enrollment)")}
if 'sunday' not in existing:
    cur.execute("ALTER TABLE daycare_enrollment ADD COLUMN sunday BOOLEAN NOT NULL DEFAULT 0")
    print("Added sunday to daycare_enrollment")
else:
    print("daycare_enrollment.sunday already exists")

existing_wl = {row[1] for row in cur.execute("PRAGMA table_info(daycare_waitlist)")}
if 'saturday' not in existing_wl:
    cur.execute("ALTER TABLE daycare_waitlist ADD COLUMN saturday BOOLEAN NOT NULL DEFAULT 0")
    print("Added saturday to daycare_waitlist")
else:
    print("daycare_waitlist.saturday already exists")

if 'sunday' not in existing_wl:
    cur.execute("ALTER TABLE daycare_waitlist ADD COLUMN sunday BOOLEAN NOT NULL DEFAULT 0")
    print("Added sunday to daycare_waitlist")
else:
    print("daycare_waitlist.sunday already exists")

con.commit()
con.close()
print("Done.")
