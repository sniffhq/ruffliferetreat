import sqlite3, os

con = sqlite3.connect('instance/rufflife.db')
rows = con.execute("SELECT key, value FROM facility_setting WHERE key='homepage_hero_photo'").fetchall()
print('DB setting:', rows)

path = 'app/static/uploads/homepage/'
files = os.listdir(path) if os.path.exists(path) else 'FOLDER MISSING'
print('Files in uploads/homepage:', files)
