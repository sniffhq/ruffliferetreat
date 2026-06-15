"""Add media_url to sms_message for MMS support

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision      = 'w9x0y1z2a3b4'
down_revision = 'v8w9x0y1z2a3'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('sms_message',
        sa.Column('media_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('sms_message', 'media_url')
