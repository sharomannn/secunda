"""Create payments and outbox tables

Revision ID: 001
Revises: 
Create Date: 2026-04-20 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    op.execute("CREATE TYPE payment_status AS ENUM ('pending', 'succeeded', 'failed')")
    op.execute("CREATE TYPE currency AS ENUM ('RUB', 'USD', 'EUR')")
    op.execute("CREATE TYPE outbox_status AS ENUM ('pending', 'published')")
    
    # Create payments table
    op.create_table(
        'payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', postgresql.ENUM('RUB', 'USD', 'EUR', name='currency'), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('status', postgresql.ENUM('pending', 'succeeded', 'failed', name='payment_status'), nullable=False, server_default='pending'),
        sa.Column('idempotency_key', sa.String(255), nullable=False, unique=True),
        sa.Column('webhook_url', sa.String(2048), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('amount > 0', name='check_amount_positive')
    )
    
    # Create indexes for payments
    op.create_index('idx_payment_idempotency_key', 'payments', ['idempotency_key'], unique=True)
    op.create_index('idx_payment_status', 'payments', ['status'])
    op.create_index('idx_payment_created_at', 'payments', [sa.text('created_at DESC')])
    
    # Create outbox table
    op.create_table(
        'outbox',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('aggregate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'published', name='outbox_status'), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create indexes for outbox
    op.create_index('idx_outbox_status', 'outbox', ['status'], postgresql_where=sa.text("status = 'pending'"))
    op.create_index('idx_outbox_created_at', 'outbox', [sa.text('created_at DESC')])
    op.create_index('idx_outbox_aggregate_id', 'outbox', ['aggregate_id'])


def downgrade() -> None:
    op.drop_table('outbox')
    op.drop_table('payments')
    op.execute('DROP TYPE outbox_status')
    op.execute('DROP TYPE currency')
    op.execute('DROP TYPE payment_status')
