"""Add vaccination alert acknowledgement fields to pet

Revision ID: x1y2z3a4b5c6
Revises: t6u7v8w9x0y1
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'x1y2z3a4b5c6'
down_revision = 'd1e2f3g4h5i6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pet', sa.Column('vacc_alert_acknowledged', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('pet', sa.Column('vacc_alert_ack_at', sa.DateTime(), nullable=True))
    op.add_column('pet', sa.Column('vacc_alert_ack_by', sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column('pet', 'vacc_alert_ack_by')
    op.drop_column('pet', 'vacc_alert_ack_at')
    op.drop_column('pet', 'vacc_alert_acknowledged')
