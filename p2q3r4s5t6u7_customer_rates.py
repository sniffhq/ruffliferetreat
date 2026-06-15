"""Add customer custom rates to user table

Revision ID: p2q3r4s5t6u7
Revises: o1p2q3r4s5t6
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa

revision      = 'p2q3r4s5t6u7'
down_revision = 'o1p2q3r4s5t6'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Boarding rates
        batch_op.add_column(sa.Column('custom_boarding_rate',
            sa.Numeric(10, 2), nullable=True,
            comment='Override nightly boarding rate for this customer'))
        batch_op.add_column(sa.Column('custom_boarding_rate_additional',
            sa.Numeric(10, 2), nullable=True,
            comment='Override additional pet boarding rate for this customer'))

        # Daycare rates
        batch_op.add_column(sa.Column('custom_daycare_rate',
            sa.Numeric(10, 2), nullable=True,
            comment='Override daycare daily rate for this customer'))

        # Add-on rates
        batch_op.add_column(sa.Column('custom_addon_spa_bath_nails',
            sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column('custom_addon_spa_bath',
            sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column('custom_addon_nail_trim',
            sa.Numeric(10, 2), nullable=True))

        # Rate notes
        batch_op.add_column(sa.Column('custom_rate_note',
            sa.String(255), nullable=True,
            comment='Reason for custom pricing (e.g. military discount, long-term client)'))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('custom_rate_note')
        batch_op.drop_column('custom_addon_nail_trim')
        batch_op.drop_column('custom_addon_spa_bath')
        batch_op.drop_column('custom_addon_spa_bath_nails')
        batch_op.drop_column('custom_daycare_rate')
        batch_op.drop_column('custom_boarding_rate_additional')
        batch_op.drop_column('custom_boarding_rate')