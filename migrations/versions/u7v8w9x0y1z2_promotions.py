"""Add promotions system

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2024-01-01

"""
from alembic import op
import sqlalchemy as sa

revision = 'u7v8w9x0y1z2'
down_revision = 't6u7v8w9x0y1'
branch_labels = None
depends_on = None


def upgrade():
    # business_settings may not exist in all deployments — skip gracefully
    try:
        op.add_column('business_settings',
            sa.Column('promotions_enabled', sa.Boolean(), nullable=True, server_default='0'))
    except Exception:
        pass


def downgrade():
    try:
        with op.batch_alter_table('business_settings', schema=None) as batch_op:
            batch_op.drop_column('promotions_enabled')
    except Exception:
        pass
