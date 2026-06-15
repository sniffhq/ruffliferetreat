"""add invoice_token table

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
Create Date: 2026-05-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'l8m9n0o1p2q3'
down_revision = 'k7l8m9n0o1p2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('invoice_token',
        sa.Column('id',          sa.Integer(),     nullable=False),
        sa.Column('customer_id', sa.Integer(),     nullable=False),
        sa.Column('token',       sa.String(64),    nullable=False),
        sa.Column('created_at',  sa.DateTime(),    nullable=True),
        sa.Column('last_sent',   sa.DateTime(),    nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index('ix_invoice_token_token', 'invoice_token', ['token'])


def downgrade():
    op.drop_index('ix_invoice_token_token', 'invoice_token')
    op.drop_table('invoice_token')