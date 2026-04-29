"""add_branding_and_custom_modules

Revision ID: a1b2c3d4e5f6
Revises: b9f3a2c1d8e7
Create Date: 2026-05-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'b9f3a2c1d8e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('branding_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.String(length=100), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('primary_color', sa.String(length=7), nullable=True),
        sa.Column('accent_color', sa.String(length=7), nullable=True),
        sa.Column('support_email', sa.String(length=255), nullable=True),
        sa.Column('custom_domain', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id'),
    )
    op.create_table('custom_modules',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('prompt_template', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_user_id', 'slug', name='uq_custom_module_owner_slug'),
    )
    op.create_index('ix_custom_modules_owner_user_id', 'custom_modules', ['owner_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_custom_modules_owner_user_id', table_name='custom_modules')
    op.drop_table('custom_modules')
    op.drop_table('branding_settings')
