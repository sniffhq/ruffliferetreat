"""Add boarding_hours_override table

Revision ID: e2f3g4h5i6j7
Revises: d1e2f3g4h5i6
Create Date: 2026-11-09

"""
from alembic import op
import sqlalchemy as sa

revision = 'e2f3g4h5i6j7'
down_revision = 'z4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'boarding_hours_override',
        sa.Column('id',             sa.Integer(),    nullable=False),
        sa.Column('override_date',  sa.Date(),       nullable=False),
        sa.Column('label',          sa.String(100),  nullable=True),
        sa.Column('dropoff_open',   sa.String(5),    nullable=True),
        sa.Column('dropoff_close',  sa.String(5),    nullable=True),
        sa.Column('dropoff_closed', sa.Boolean(),    nullable=False, server_default='0'),
        sa.Column('pickup_open',    sa.String(5),    nullable=True),
        sa.Column('pickup_close',   sa.String(5),    nullable=True),
        sa.Column('pickup_closed',  sa.Boolean(),    nullable=False, server_default='0'),
        sa.Column('created_by',     sa.Integer(),    nullable=True),
        sa.Column('created_at',     sa.DateTime(),   nullable=True),
        sa.Column('updated_at',     sa.DateTime(),   nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('override_date'),
    )
    op.create_index('ix_boarding_hours_override_date', 'boarding_hours_override', ['override_date'])


def downgrade():
    op.drop_index('ix_boarding_hours_override_date', 'boarding_hours_override')
    op.drop_table('boarding_hours_override')
