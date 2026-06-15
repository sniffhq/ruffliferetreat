"""add daily_log and daily_log_pet_flag tables

Revision ID: o1p2q3r4s5t6
Revises: n0o1p2q3r4s5
Create Date: 2026-06-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'o1p2q3r4s5t6'
down_revision = 'n0o1p2q3r4s5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('daily_log',
        sa.Column('id',         sa.Integer(),  nullable=False),
        sa.Column('log_date',   sa.Date(),     nullable=False),
        sa.Column('author_id',  sa.Integer(),  nullable=False),
        sa.Column('notes',      sa.Text(),     nullable=True),
        sa.Column('incidents',  sa.Text(),     nullable=True),
        sa.Column('staffing',   sa.Text(),     nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_daily_log_log_date', 'daily_log', ['log_date'])

    op.create_table('daily_log_pet_flag',
        sa.Column('id',        sa.Integer(),     nullable=False),
        sa.Column('log_id',    sa.Integer(),     nullable=False),
        sa.Column('pet_id',    sa.Integer(),     nullable=False),
        sa.Column('flag_type', sa.String(50),    nullable=True),
        sa.Column('note',      sa.String(255),   nullable=True),
        sa.ForeignKeyConstraint(['log_id'], ['daily_log.id']),
        sa.ForeignKeyConstraint(['pet_id'], ['pet.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('daily_log_pet_flag')
    op.drop_index('ix_daily_log_log_date', table_name='daily_log')
    op.drop_table('daily_log')