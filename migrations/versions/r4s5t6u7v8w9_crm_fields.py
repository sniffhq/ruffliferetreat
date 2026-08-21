"""Add CRM fields to user table
Revision ID: r4s5t6u7v8w9
Revises: p2q3r4s5t6u7
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa

revision      = 'r4s5t6u7v8w9'
down_revision = 'p2q3r4s5t6u7'
branch_labels = None
depends_on    = None


def upgrade():
    from sqlalchemy import inspect
    bind = op.get_bind()
    existing = [c['name'] for c in inspect(bind).get_columns('user')]
    with op.batch_alter_table('user', schema=None) as batch_op:
        if 'staff_notes' not in existing:
            batch_op.add_column(sa.Column(
                'staff_notes',
                sa.Text(),
                nullable=True,
                comment='Internal staff notes about this customer'
            ))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('staff_notes')
