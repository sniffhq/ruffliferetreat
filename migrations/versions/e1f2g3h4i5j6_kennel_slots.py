"""Add kennel_slot table with static facility layout

Revision ID: e1f2g3h4i5j6
Revises: d1e2f3g4h5i6
Create Date: 2026-06-23

Layout:
  Suites  1-16
  Kennels 17-55  (51-55 small dogs only)
"""
from alembic import op
import sqlalchemy as sa

revision      = 'e1f2g3h4i5j6'
down_revision = 'd1e2f3g4h5i6'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'kennel_slot',
        sa.Column('id',            sa.Integer,     primary_key=True),
        sa.Column('kennel_type',   sa.String(10),  nullable=False),
        sa.Column('kennel_number', sa.String(20),  nullable=False),
        sa.Column('notes',         sa.String(100), nullable=True),
        sa.Column('active',        sa.Boolean,     nullable=False, server_default='1'),
        sa.Column('sort_order',    sa.Integer,     nullable=False, server_default='0'),
        sa.UniqueConstraint('kennel_type', 'kennel_number', name='uq_kennel_slot'),
    )

    conn = op.get_bind()

    # Suites 1-16
    for n in range(1, 17):
        conn.execute(sa.text(
            "INSERT INTO kennel_slot (kennel_type, kennel_number, notes, active, sort_order) "
            "VALUES ('suite', :num, NULL, 1, :order)"
        ), {"num": str(n), "order": n})

    # Kennels 17-50
    for n in range(17, 51):
        conn.execute(sa.text(
            "INSERT INTO kennel_slot (kennel_type, kennel_number, notes, active, sort_order) "
            "VALUES ('kennel', :num, NULL, 1, :order)"
        ), {"num": str(n), "order": n})

    # Kennels 51-55 — small dogs only
    for n in range(51, 56):
        conn.execute(sa.text(
            "INSERT INTO kennel_slot (kennel_type, kennel_number, notes, active, sort_order) "
            "VALUES ('kennel', :num, 'Small dogs only', 1, :order)"
        ), {"num": str(n), "order": n})


def downgrade():
    op.drop_table('kennel_slot')
