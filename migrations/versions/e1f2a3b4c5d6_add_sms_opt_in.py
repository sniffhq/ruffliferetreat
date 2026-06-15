"""add sms_opt_in to user

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(
            sa.Column('sms_opt_in', sa.Boolean(), nullable=True, server_default='0')
        )


def downgrade():
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('sms_opt_in')