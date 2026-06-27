"""Add waived columns to daycare_attendance

Revision ID: dc3f8a921b04
Revises: z4a5b6c7d8e9
Create Date: 2026-06-26

"""
from alembic import op
import sqlalchemy as sa

revision = 'dc3f8a921b04'
down_revision = 'z4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('daycare_attendance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('waived', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('waived_by', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('waived_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('daycare_attendance', schema=None) as batch_op:
        batch_op.drop_column('waived_at')
        batch_op.drop_column('waived_by')
        batch_op.drop_column('waived')
