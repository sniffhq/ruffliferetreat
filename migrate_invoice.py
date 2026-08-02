"""
Migration: Create invoice table
Run from the RuffLifeRetreat project root:
    python migrate_invoice.py
"""
import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'rufflife.db')
if not os.path.exists(DB_PATH):
    print(f'ERROR: Database not found at {DB_PATH}')
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Check if table already exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invoice'")
if cur.fetchone():
    print('invoice table already exists — nothing to do.')
    conn.close()
    sys.exit(0)

print('Creating invoice table...')
cur.executescript("""
CREATE TABLE IF NOT EXISTS invoice (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number VARCHAR(20) UNIQUE NOT NULL,
    customer_id    INTEGER NOT NULL REFERENCES user(id),
    boarding_id    INTEGER REFERENCES boarding(id),
    service_type   VARCHAR(20) NOT NULL DEFAULT 'boarding',
    line_items     TEXT NOT NULL DEFAULT '[]',
    subtotal       FLOAT NOT NULL DEFAULT 0.0,
    total          FLOAT NOT NULL DEFAULT 0.0,
    status         VARCHAR(20) NOT NULL DEFAULT 'draft',
    generated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    generated_by   INTEGER REFERENCES user(id),
    sent_at        DATETIME,
    paid_at        DATETIME,
    payment_method VARCHAR(30),
    voided_at      DATETIME,
    voided_reason  VARCHAR(255),
    notes          TEXT,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invoice_customer ON invoice(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoice_boarding ON invoice(boarding_id);
CREATE INDEX IF NOT EXISTS idx_invoice_status   ON invoice(status);
""")

conn.commit()
conn.close()
print('Done. invoice table created successfully.')
