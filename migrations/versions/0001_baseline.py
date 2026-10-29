"""Baseline: schema of the original application (users, categories, products, cart, orders).

Revision ID: 0001_baseline
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone', sa.String(12), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.String(200), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('phone'),
    )
    op.create_index('ix_users_phone', 'users', ['phone'])
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('slug', sa.String(80), nullable=False),
        sa.Column('visible', sa.Boolean(), nullable=False),
        sa.Column('image_url', sa.String(300)),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug'),
    )
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('slug', sa.String(150), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('stock', sa.Integer()),
        sa.Column('image_url', sa.String(300)),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id')),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('is_active', sa.Boolean()),
        sa.UniqueConstraint('slug'),
    )
    op.create_table(
        'cart_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Integer()),
    )
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(20)),
        sa.Column('total_amount', sa.Numeric(10, 2)),
        sa.Column('shipping_address', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price_at_purchase', sa.Numeric(10, 2), nullable=False),
    )


def downgrade():
    for t in ('order_items', 'orders', 'cart_items', 'products', 'categories', 'users'):
        op.drop_table(t)
