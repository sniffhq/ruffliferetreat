"""Add booking_number to boarding table

Revision ID: c0d1e2f3a4b5
Revises: b7c8d9e0f1a2
Create Date: 2026-06-22

"""
from alembic import op
import sqlalchemy as sa

revision      = 'c0d1e2f3a4b5'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('boarding',
        sa.Column('booking_number', sa.String(20), nullable=True))
    op.create_unique_constraint('uq_boarding_booking_number', 'boarding', ['booking_number'])


def downgrade():
    op.drop_constraint('uq_boarding_booking_number', 'boarding', type_='unique')
    op.drop_column('boarding', 'booking_number')
