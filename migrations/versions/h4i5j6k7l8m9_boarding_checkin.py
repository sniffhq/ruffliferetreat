"""add checked_in fields to boarding

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-05-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'h4i5j6k7l8m9'
down_revision = 'g3h4i5j6k7l8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('boarding') as batch_op:
        batch_op.add_column(sa.Column('checked_in', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('checked_in_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('boarding') as batch_op:
        batch_op.drop_column('checked_in_at')
        batch_op.drop_column('checked_in')