"""Add service interest to user and user_id to daycare_waitlist

Revision ID: z4a5b6c7d8e9
Revises: y3z4a5b6c7d8
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision      = 'z4a5b6c7d8e9'
down_revision = 'y3z4a5b6c7d8'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('user',
        sa.Column('interested_in_daycare', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('user',
        sa.Column('interested_in_boarding', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('daycare_waitlist',
        sa.Column('user_id', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('daycare_waitlist', 'user_id')
    op.drop_column('user', 'interested_in_boarding')
    op.drop_column('user', 'interested_in_daycare')
