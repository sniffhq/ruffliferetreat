"""Add per-pet custom rate fields to pet table

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
Create Date: 2026-06-05

"""
from alembic import op
import sqlalchemy as sa

revision      = 's5t6u7v8w9x0'
down_revision = 'q3r4s5t6u7v8'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('pet', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'custom_boarding_rate',
            sa.Numeric(10, 2),
            nullable=True,
            comment='Per-pet boarding rate override — overrides customer and facility rates'
        ))
        batch_op.add_column(sa.Column(
            'custom_daycare_rate',
            sa.Numeric(10, 2),
            nullable=True,
            comment='Per-pet daycare rate override'
        ))
        batch_op.add_column(sa.Column(
            'custom_rate_note',
            sa.String(255),
            nullable=True,
            comment='Reason for per-pet custom rate'
        ))


def downgrade():
    with op.batch_alter_table('pet', schema=None) as batch_op:
        batch_op.drop_column('custom_rate_note')
        batch_op.drop_column('custom_daycare_rate')
        batch_op.drop_column('custom_boarding_rate')