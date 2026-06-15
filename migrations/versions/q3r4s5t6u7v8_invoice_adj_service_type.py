"""Add service_type to invoice_adjustment

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-06-03

"""
from alembic import op
import sqlalchemy as sa

revision      = 'q3r4s5t6u7v8'
down_revision = 'p2q3r4s5t6u7'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('invoice_adjustment', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'service_type',
            sa.String(20),
            nullable=True,
            server_default='boarding',
            comment="'boarding' or 'daycare' — scopes adjustment to a specific invoice type"
        ))


def downgrade():
    with op.batch_alter_table('invoice_adjustment', schema=None) as batch_op:
        batch_op.drop_column('service_type')