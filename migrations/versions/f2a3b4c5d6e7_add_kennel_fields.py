"""add kennel fields to boarding

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('boarding') as batch_op:
        batch_op.add_column(sa.Column('kennel_number', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('kennel_type', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('boarding') as batch_op:
        batch_op.drop_column('kennel_type')
        batch_op.drop_column('kennel_number')