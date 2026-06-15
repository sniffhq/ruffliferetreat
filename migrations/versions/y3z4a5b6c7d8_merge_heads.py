"""Merge sms_media_url and appointment_cancel_acknowledged heads

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7, z3a4b5c6d7e8
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision      = 'y3z4a5b6c7d8'
down_revision = ('x2y3z4a5b6c7', 'z3a4b5c6d7e8')
branch_labels = None
depends_on    = None


def upgrade():
    pass


def downgrade():
    pass
