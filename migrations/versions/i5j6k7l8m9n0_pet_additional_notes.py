"""add additional_notes to pet

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-05-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'i5j6k7l8m9n0'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pet') as batch_op:
        batch_op.add_column(sa.Column('additional_notes', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('pet') as batch_op:
        batch_op.drop_column('additional_notes')