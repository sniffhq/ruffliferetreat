"""Add pet_tags to pet table

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-06-05

"""
from alembic import op
import sqlalchemy as sa

revision      = 't6u7v8w9x0y1'
down_revision = 's5t6u7v8w9x0'
branch_labels = None
depends_on    = None


def upgrade():
    with op.batch_alter_table('pet', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'pet_tags',
            sa.Text(),
            nullable=True,
            comment='Comma-separated pet tags e.g. "Needs Medication,Senior,Dog Aggressive"'
        ))


def downgrade():
    with op.batch_alter_table('pet', schema=None) as batch_op:
        batch_op.drop_column('pet_tags')
