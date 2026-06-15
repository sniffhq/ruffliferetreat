"""add special_rate to daycare_enrollment

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2026-05-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'm9n0o1p2q3r4'
down_revision = 'l8m9n0o1p2q3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('daycare_enrollment') as batch_op:
        batch_op.add_column(sa.Column('special_rate', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('daycare_enrollment') as batch_op:
        batch_op.drop_column('special_rate')