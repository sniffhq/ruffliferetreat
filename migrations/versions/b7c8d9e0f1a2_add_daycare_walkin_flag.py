"""Add is_walkin flag to daycare_enrollment

Revision ID: b7c8d9e0f1a2
Revises: 9f8e7d6c5b4a
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision      = 'b7c8d9e0f1a2'
down_revision = '9f8e7d6c5b4a'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('daycare_enrollment',
        sa.Column('is_walkin', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('daycare_enrollment', 'is_walkin')
