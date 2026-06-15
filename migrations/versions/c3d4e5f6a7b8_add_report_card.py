"""add report_card table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('report_card',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pet_id', sa.Integer(), nullable=False),
        sa.Column('card_type', sa.String(length=10), nullable=False),
        sa.Column('card_date', sa.Date(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('mood', sa.String(length=20), nullable=True),
        sa.Column('energy', sa.String(length=20), nullable=True),
        sa.Column('played_well', sa.String(length=20), nullable=True),
        sa.Column('hydrated', sa.Boolean(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('photo_filename', sa.String(length=255), nullable=True),
        sa.Column('appetite', sa.String(length=20), nullable=True),
        sa.Column('sleep', sa.String(length=20), nullable=True),
        sa.Column('temperament', sa.String(length=20), nullable=True),
        sa.Column('medications_given', sa.Boolean(), nullable=True),
        sa.Column('bathroom', sa.String(length=20), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pet_id'], ['pet.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )


def downgrade():
    op.drop_table('report_card')