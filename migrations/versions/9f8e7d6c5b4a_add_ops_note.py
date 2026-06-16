"""Add OpsNote model for operational pet and day notes

Revision ID: 9f8e7d6c5b4a
Revises: z4a5b6c7d8e9
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision      = '9f8e7d6c5b4a'
down_revision = 'z4a5b6c7d8e9'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'ops_note',
        sa.Column('id',         sa.Integer(),     nullable=False),
        sa.Column('note_date',  sa.Date(),        nullable=False),
        sa.Column('pet_id',     sa.Integer(),     nullable=True),
        sa.Column('note',       sa.String(500),   nullable=False),
        sa.Column('flag_type',  sa.String(20),    nullable=True),
        sa.Column('created_by', sa.Integer(),     nullable=True),
        sa.Column('created_at', sa.DateTime(),    nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['pet_id'],     ['pet.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ops_note_note_date', 'ops_note', ['note_date'])


def downgrade():
    op.drop_index('ix_ops_note_note_date', table_name='ops_note')
    op.drop_table('ops_note')
