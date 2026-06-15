"""Add waiver_accepted fields to user

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-06-06

"""
from alembic import op
import sqlalchemy as sa

revision      = 'v8w9x0y1z2a3'
down_revision = 't6u7v8w9x0y1'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column('user', sa.Column('waiver_accepted',    sa.Boolean(),  nullable=True, server_default='0'))
    op.add_column('user', sa.Column('waiver_accepted_at', sa.DateTime(), nullable=True))

    # Backfill: existing customers who completed onboarding are treated as having accepted
    op.execute("""
        UPDATE user
        SET waiver_accepted = 1,
            waiver_accepted_at = created_at
        WHERE onboarding_complete = 1
          AND role = 'customer'
    """)


def downgrade():
    op.drop_column('user', 'waiver_accepted_at')
    op.drop_column('user', 'waiver_accepted')