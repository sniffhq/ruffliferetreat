"""add sms_message table

Revision ID: 9e8591817833
Revises: f2be576a1519
Create Date: 2026-04-26 16:28:13.016873

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9e8591817833'
down_revision = 'f2be576a1519'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sms_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('from_number', sa.String(length=20), nullable=False),
    sa.Column('to_number', sa.String(length=20), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('twilio_sid', sa.String(length=64), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('sms_message')