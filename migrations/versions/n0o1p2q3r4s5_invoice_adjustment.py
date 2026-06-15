"""add invoice_adjustment table

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
Create Date: 2026-05-31 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'n0o1p2q3r4s5'
down_revision = 'm9n0o1p2q3r4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('invoice_adjustment',
        sa.Column('id',          sa.Integer(),     nullable=False),
        sa.Column('customer_id', sa.Integer(),     nullable=False),
        sa.Column('adj_type',    sa.String(20),    nullable=False),
        sa.Column('line_key',    sa.String(100),   nullable=True),
        sa.Column('description', sa.String(200),   nullable=False),
        sa.Column('amount',      sa.Float(),       nullable=False),
        sa.Column('created_by',  sa.Integer(),     nullable=True),
        sa.Column('created_at',  sa.DateTime(),    nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['user.id']),
        sa.ForeignKeyConstraint(['created_by'],  ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('invoice_adjustment')