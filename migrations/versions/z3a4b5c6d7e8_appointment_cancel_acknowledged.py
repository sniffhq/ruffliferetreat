"""Add cancel_acknowledged flag to appointment

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'z3a4b5c6d7e8'
down_revision = 'y2z3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('appointment', sa.Column(
        'cancel_acknowledged', sa.Boolean(), nullable=False, server_default='0'
    ))


def downgrade():
    op.drop_column('appointment', 'cancel_acknowledged')
