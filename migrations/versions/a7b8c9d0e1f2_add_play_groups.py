"""add play group management

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # Create play_group table first
    op.create_table('play_group',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('size_category', sa.String(length=20), nullable=False),
        sa.Column('temperament', sa.String(length=20), nullable=False),
        sa.Column('max_capacity', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('color', sa.String(length=7), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Add play_group_id to daycare_attendance using batch mode
    with op.batch_alter_table('daycare_attendance') as batch_op:
        batch_op.add_column(
            sa.Column('play_group_id', sa.Integer(), nullable=True)
        )

    # Add temperament and default_play_group_id to pet using batch mode
    with op.batch_alter_table('pet') as batch_op:
        batch_op.add_column(
            sa.Column('temperament', sa.String(length=20), nullable=True)
        )
        batch_op.add_column(
            sa.Column('default_play_group_id', sa.Integer(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('pet') as batch_op:
        batch_op.drop_column('default_play_group_id')
        batch_op.drop_column('temperament')

    with op.batch_alter_table('daycare_attendance') as batch_op:
        batch_op.drop_column('play_group_id')

    op.drop_table('play_group')