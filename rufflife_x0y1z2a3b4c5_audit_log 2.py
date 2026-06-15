"""Add audit log table

Revision ID: x0y1z2a3b4c5
Revises: w9x0y1z2a3b4
Create Date: 2026-06-08

"""
from alembic import op
import sqlalchemy as sa

revision      = 'x0y1z2a3b4c5'
down_revision = 'w9x0y1z2a3b4'
branch_labels = None
depends_on    = None


def upgrade():
    conn   = op.get_bind()
    tables = [r[0] for r in conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
    if 'audit_log' not in tables:
        op.create_table('audit_log',
            sa.Column('id',          sa.Integer(),     primary_key=True),
            sa.Column('timestamp',   sa.DateTime(),    nullable=False),
            sa.Column('user_id',     sa.Integer(),     sa.ForeignKey('user.id'), nullable=True),
            sa.Column('user_email',  sa.String(120),   nullable=True),
            sa.Column('user_name',   sa.String(100),   nullable=True),
            sa.Column('action',      sa.String(80),    nullable=False),
            sa.Column('entity_type', sa.String(50),    nullable=True),
            sa.Column('entity_id',   sa.Integer(),     nullable=True),
            sa.Column('entity_name', sa.String(200),   nullable=True),
            sa.Column('description', sa.Text(),        nullable=True),
            sa.Column('ip_address',  sa.String(45),    nullable=True),
            sa.Column('extra_data',  sa.Text(),        nullable=True),
        )


def downgrade():
    op.drop_table('audit_log')
