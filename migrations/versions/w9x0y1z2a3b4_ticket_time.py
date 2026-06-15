"""Add ticket time sessions

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-06-06

"""
from alembic import op
import sqlalchemy as sa

revision      = 'w9x0y1z2a3b4'
down_revision = 'v8w9x0y1z2a3'
branch_labels = None
depends_on    = None


def upgrade():
    import sqlite3
    from alembic import op as _op
    # Only add columns if they don't already exist
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(support_ticket)")).fetchall()]
    if 'total_minutes' not in cols:
        op.add_column('support_ticket', sa.Column('total_minutes', sa.Integer(), nullable=True, server_default='0'))
    if 'active_session_started' not in cols:
        op.add_column('support_ticket', sa.Column('active_session_started', sa.DateTime(), nullable=True))
    if 'active_session_user_id' not in cols:
        op.add_column('support_ticket', sa.Column('active_session_user_id', sa.Integer(),
                                                   sa.ForeignKey('user.id'), nullable=True))
    # Time session log
    tables = [row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
    if 'ticket_time_session' not in tables:
        op.create_table('ticket_time_session',
        sa.Column('id',          sa.Integer(),  primary_key=True),
        sa.Column('ticket_id',   sa.Integer(),  sa.ForeignKey('support_ticket.id'), nullable=False),
        sa.Column('user_id',     sa.Integer(),  sa.ForeignKey('user.id'),           nullable=True),
        sa.Column('started_at',  sa.DateTime(), nullable=False),
        sa.Column('ended_at',    sa.DateTime(), nullable=True),
        sa.Column('minutes',     sa.Integer(),  nullable=True),
        sa.Column('note',        sa.String(200), nullable=True),
    )


def downgrade():
    op.drop_table('ticket_time_session')
    op.drop_column('support_ticket', 'active_session_user_id')
    op.drop_column('support_ticket', 'active_session_started')
    op.drop_column('support_ticket', 'total_minutes')