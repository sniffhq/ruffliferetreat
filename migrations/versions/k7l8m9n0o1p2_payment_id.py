"""add payment_id to boarding and daycare_attendance

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
Create Date: 2026-05-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'k7l8m9n0o1p2'
down_revision = 'j6k7l8m9n0o1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('boarding') as batch_op:
        batch_op.add_column(sa.Column('payment_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_boarding_payment', 'payment', ['payment_id'], ['id'])

    with op.batch_alter_table('daycare_attendance') as batch_op:
        batch_op.add_column(sa.Column('payment_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_attendance_payment', 'payment', ['payment_id'], ['id'])


def downgrade():
    with op.batch_alter_table('daycare_attendance') as batch_op:
        batch_op.drop_constraint('fk_attendance_payment', type_='foreignkey')
        batch_op.drop_column('payment_id')

    with op.batch_alter_table('boarding') as batch_op:
        batch_op.drop_constraint('fk_boarding_payment', type_='foreignkey')
        batch_op.drop_column('payment_id')