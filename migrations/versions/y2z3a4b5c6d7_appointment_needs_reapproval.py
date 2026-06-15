"""Add needs_reapproval flag to appointment

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'y2z3a4b5c6d7'
down_revision = 'x1y2z3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('appointment', sa.Column(
        'needs_reapproval', sa.Boolean(), nullable=False, server_default='0'
    ))


def downgrade():
    op.drop_column('appointment', 'needs_reapproval')
