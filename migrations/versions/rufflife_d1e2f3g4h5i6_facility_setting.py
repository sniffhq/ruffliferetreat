"""Add facility_setting table

Revision ID: d1e2f3g4h5i6
Revises: rufflife_x0y1z2a3b4c5_audit_log
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision      = 'd1e2f3g4h5i6'
down_revision = 'x0y1z2a3b4c5'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table('facility_setting',
        sa.Column('id',         sa.Integer(),     nullable=False),
        sa.Column('key',        sa.String(80),    nullable=False),
        sa.Column('value',      sa.String(255),   nullable=False),
        sa.Column('updated_at', sa.DateTime(),    nullable=True),
        sa.Column('updated_by', sa.Integer(),     sa.ForeignKey('user.id'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    # Seed default kennel capacity
    op.execute("INSERT INTO facility_setting (key, value) VALUES ('kennel_capacity', '40')")


def downgrade():
    op.drop_table('facility_setting')
