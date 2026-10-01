"""
Migration: Add jira_key / jira_url columns to support_ticket
Run from the RuffLifeRetreat project root:
    python migrate_jira_fields.py
"""
import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'rufflife.db')
if not os.path.exists(DB_PATH):
    print(f'ERROR: Database not found at {DB_PATH}')
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute("PRAGMA table_info(support_ticket)")
existing_cols = {row[1] for row in cur.fetchall()}

added = False
if 'jira_key' not in existing_cols:
    print('Adding jira_key column...')
    cur.execute('ALTER TABLE support_ticket ADD COLUMN jira_key VARCHAR(20)')
    added = True
else:
    print('jira_key column already exists — skipping.')

if 'jira_url' not in existing_cols:
    print('Adding jira_url column...')
    cur.execute('ALTER TABLE support_ticket ADD COLUMN jira_url VARCHAR(255)')
    added = True
else:
    print('jira_url column already exists — skipping.')

if added:
    conn.commit()
    print('Done.')
else:
    print('Nothing to do.')

conn.close()
