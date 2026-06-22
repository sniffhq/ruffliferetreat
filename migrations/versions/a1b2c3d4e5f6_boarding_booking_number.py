"""Add booking_number to boarding table

Revision ID: a1b2c3d4e5f6
Revises: z4a5b6c7d8e9
Create Date: 2026-06-22

"""
from alembic import op
import sqlalchemy as sa

revision      = 'a1b2c3d4e5f6'
down_revision = 'z4a5b6c7d8e9'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('boarding',
        sa.Column('booking_number', sa.String(20), nullable=True))
    op.create_unique_constraint('uq_boarding_booking_number', 'boarding', ['booking_number'])


def downgrade():
    op.drop_constraint('uq_boarding_booking_number', 'boarding', type_='unique')
    op.drop_column('boarding', 'booking_number')
