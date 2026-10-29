"""Catalog, variants, recursive categories, orders, payments, SMS

Revision ID: 0002_upgrade
Revises: 0001_baseline
Create Date: 2026-10-23 11:05:54.205977

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0002_upgrade'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None



def upgrade():
    op.create_table('attributes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('slug', sa.String(length=60), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('coupons',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('value', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('min_subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('max_discount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('usage_limit', sa.Integer(), nullable=True),
    sa.Column('per_user_limit', sa.Integer(), nullable=True),
    sa.Column('used_count', sa.Integer(), nullable=False),
    sa.Column('starts_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('shipping_methods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('free_over', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('store_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('store_name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('logo_url', sa.String(length=300), nullable=True),
    sa.Column('favicon_url', sa.String(length=300), nullable=True),
    sa.Column('domain', sa.String(length=120), nullable=True),
    sa.Column('contact_email', sa.String(length=120), nullable=True),
    sa.Column('contact_phone', sa.String(length=30), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('banner_image_url', sa.String(length=300), nullable=True),
    sa.Column('banner_title', sa.String(length=150), nullable=True),
    sa.Column('banner_link', sa.String(length=300), nullable=True),
    sa.Column('social_links', sa.JSON(), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('locale', sa.String(length=8), nullable=False),
    sa.Column('shipping_info', sa.Text(), nullable=True),
    sa.Column('return_policy', sa.Text(), nullable=True),
    sa.Column('seo_title', sa.String(length=150), nullable=True),
    sa.Column('seo_description', sa.String(length=300), nullable=True),
    sa.Column('seo_keywords', sa.String(length=300), nullable=True),
    sa.Column('og_image_url', sa.String(length=300), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('slug', sa.String(length=60), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('verification_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('code_hash', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('consumed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('verification_codes', schema=None) as batch_op:
        batch_op.create_index('ix_vc_phone_purpose', ['phone', 'purpose', 'created_at'], unique=False)

    op.create_table('addresses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=50), nullable=True),
    sa.Column('recipient_name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('city', sa.String(length=80), nullable=True),
    sa.Column('address_line', sa.Text(), nullable=False),
    sa.Column('postal_code', sa.String(length=20), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('addresses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_addresses_user_id'), ['user_id'], unique=False)

    op.create_table('homepage_sections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('source_category_id', sa.Integer(), nullable=True),
    sa.Column('include_subcategories', sa.Boolean(), nullable=False),
    sa.Column('product_limit', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('visible', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['source_category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('order_status_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('changed_by_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('order_status_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_order_status_history_order_id'), ['order_id'], unique=False)

    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('gateway', sa.String(length=20), nullable=False),
    sa.Column('authority', sa.String(length=64), nullable=True),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('gateway_amount', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('ref_id', sa.String(length=64), nullable=True),
    sa.Column('card_pan', sa.String(length=32), nullable=True),
    sa.Column('error_code', sa.String(length=20), nullable=True),
    sa.Column('error_message', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('verified_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('authority')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_order_id'), ['order_id'], unique=False)

    op.create_table('product_attribute_values',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('attribute_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.String(length=100), nullable=False),
    sa.Column('value_slug', sa.String(length=110), nullable=False),
    sa.ForeignKeyConstraint(['attribute_id'], ['attributes.id'], ),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'attribute_id', 'value_slug', name='uq_pav')
    )
    with op.batch_alter_table('product_attribute_values', schema=None) as batch_op:
        batch_op.create_index('ix_pav_attr_value', ['attribute_id', 'value_slug'], unique=False)
        batch_op.create_index(batch_op.f('ix_product_attribute_values_product_id'), ['product_id'], unique=False)

    op.create_table('product_categories',
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('product_id', 'category_id')
    )
    with op.batch_alter_table('product_categories', schema=None) as batch_op:
        batch_op.create_index('ix_product_categories_category', ['category_id'], unique=False)

    op.create_table('product_images',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=400), nullable=False),
    sa.Column('alt_text', sa.String(length=200), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('product_images', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_images_product_id'), ['product_id'], unique=False)

    op.create_table('product_tags',
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('product_id', 'tag_id')
    )
    with op.batch_alter_table('product_tags', schema=None) as batch_op:
        batch_op.create_index('ix_product_tags_tag', ['tag_id'], unique=False)

    op.create_table('product_variants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=80), nullable=True),
    sa.Column('option_key', sa.String(length=300), nullable=False),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('sale_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('stock', sa.Integer(), nullable=False),
    sa.Column('reserved', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.CheckConstraint('reserved >= 0', name='ck_variant_reserved'),
    sa.CheckConstraint('stock >= 0', name='ck_variant_stock'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('product_id', 'option_key', name='uq_variant_product_optionkey'),
    sa.UniqueConstraint('sku')
    )
    with op.batch_alter_table('product_variants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_product_variants_product_id'), ['product_id'], unique=False)

    op.create_table('reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('verified_purchase', sa.Boolean(), nullable=False),
    sa.Column('is_approved', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_review_rating'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'product_id', name='uq_review_user_product')
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reviews_product_id'), ['product_id'], unique=False)

    op.create_table('sms_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dedupe_key', sa.String(length=120), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('purpose', sa.String(length=40), nullable=False),
    sa.Column('template', sa.String(length=40), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=True),
    sa.Column('provider_message_id', sa.String(length=40), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(length=300), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key')
    )
    with op.batch_alter_table('sms_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sms_logs_phone'), ['phone'], unique=False)
        batch_op.create_index(batch_op.f('ix_sms_logs_status'), ['status'], unique=False)

    op.create_table('wishlist_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'product_id', name='uq_wishlist')
    )
    with op.batch_alter_table('wishlist_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wishlist_items_user_id'), ['user_id'], unique=False)

    op.create_table('variant_options',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('variant_id', sa.Integer(), nullable=False),
    sa.Column('group_key', sa.String(length=60), nullable=False),
    sa.Column('value_key', sa.String(length=80), nullable=False),
    sa.Column('value_label', sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('variant_id', 'group_key', name='uq_variant_group')
    )
    with op.batch_alter_table('variant_options', schema=None) as batch_op:
        batch_op.create_index('ix_variant_options_lookup', ['group_key', 'value_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_variant_options_variant_id'), ['variant_id'], unique=False)

    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---- A. additive columns (server defaults so existing rows stay valid)
    with op.batch_alter_table('users') as b:
        b.add_column(sa.Column('phone_verified', sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column('sms_marketing_consent', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('marketing_consent_at', sa.DateTime()))
        b.add_column(sa.Column('marketing_opt_out_at', sa.DateTime()))
        b.add_column(sa.Column('failed_logins', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('locked_until', sa.DateTime()))
        b.add_column(sa.Column('is_active_account', sa.Boolean(), nullable=False, server_default=sa.true()))

    uq_name = 'categories_name_key' if dialect == 'postgresql' else 'uq_categories_name'
    conv = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}
    with op.batch_alter_table('categories', naming_convention=conv) as b:
        b.add_column(sa.Column('parent_id', sa.Integer()))
        b.add_column(sa.Column('path', sa.String(500), server_default=''))
        b.add_column(sa.Column('depth', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('is_internal', sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column('public_effective', sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column('description', sa.Text(), server_default=''))
        b.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
        b.drop_constraint(uq_name, type_='unique')
        b.create_foreign_key('fk_categories_parent', 'categories', ['parent_id'], ['id'])
        b.create_index('ix_categories_parent_id', ['parent_id'])
        b.create_index('ix_categories_path', ['path'])
        b.create_index('ix_categories_public_effective', ['public_effective'])
        b.create_unique_constraint('uq_categories_parent_name', ['parent_id', 'name'])

    with op.batch_alter_table('products') as b:
        b.add_column(sa.Column('brand', sa.String(80), server_default=''))
        b.add_column(sa.Column('sku', sa.String(64)))
        b.add_column(sa.Column('sale_price', sa.Numeric(12, 2)))
        b.add_column(sa.Column('min_price', sa.Numeric(12, 2)))
        b.add_column(sa.Column('status', sa.String(12), nullable=False, server_default='published'))
        b.add_column(sa.Column('options', sa.JSON()))
        b.add_column(sa.Column('updated_at', sa.DateTime()))
        b.alter_column('price', existing_type=sa.Numeric(10, 2), type_=sa.Numeric(12, 2), existing_nullable=False)
        b.create_unique_constraint('uq_products_sku', ['sku'])
        b.create_index('ix_products_brand', ['brand'])
        b.create_index('ix_products_status', ['status'])
        b.create_index('ix_products_min_price', ['min_price'])
        b.create_index('ix_products_created_at', ['created_at'])
        b.create_index('ix_products_category_id', ['category_id'])
        b.create_index('ix_products_status_created', ['status', 'created_at'])

    with op.batch_alter_table('cart_items') as b:
        b.add_column(sa.Column('variant_id', sa.Integer()))
        b.create_foreign_key('fk_cart_variant', 'product_variants', ['variant_id'], ['id'])
        b.create_index('ix_cart_items_variant_id', ['variant_id'])

    with op.batch_alter_table('orders') as b:
        b.add_column(sa.Column('payment_status', sa.String(20), nullable=False, server_default='unpaid'))
        b.add_column(sa.Column('payment_method', sa.String(20), nullable=False, server_default='cod'))
        for c in ('subtotal', 'discount_total', 'shipping_total'):
            b.add_column(sa.Column(c, sa.Numeric(12, 2), nullable=False, server_default='0'))
        b.add_column(sa.Column('currency', sa.String(8), server_default='USD'))
        b.add_column(sa.Column('coupon_id', sa.Integer()))
        b.add_column(sa.Column('coupon_code', sa.String(40)))
        b.add_column(sa.Column('shipping_method_code', sa.String(30)))
        b.add_column(sa.Column('shipping_method_name', sa.String(80)))
        b.add_column(sa.Column('ship_name', sa.String(100), server_default=''))
        b.add_column(sa.Column('ship_phone', sa.String(20), server_default=''))
        b.add_column(sa.Column('ship_city', sa.String(80), server_default=''))
        b.add_column(sa.Column('ship_postal_code', sa.String(20), server_default=''))
        b.add_column(sa.Column('shipment_provider', sa.String(80)))
        b.add_column(sa.Column('tracking_code', sa.String(80)))
        for c in ('reserved_until', 'paid_at', 'preparing_at', 'shipped_at', 'received_at', 'cancelled_at', 'updated_at'):
            b.add_column(sa.Column(c, sa.DateTime()))
        b.create_foreign_key('fk_orders_coupon', 'coupons', ['coupon_id'], ['id'])
        b.create_index('ix_orders_user_id', ['user_id'])
        b.create_index('ix_orders_created_at', ['created_at'])
        b.create_index('ix_orders_status_created', ['status', 'created_at'])

    with op.batch_alter_table('order_items') as b:
        b.add_column(sa.Column('variant_id', sa.Integer()))
        b.add_column(sa.Column('product_name', sa.String(150), server_default=''))
        b.add_column(sa.Column('sku', sa.String(80), server_default=''))
        b.add_column(sa.Column('variant_label', sa.String(200), server_default=''))
        b.add_column(sa.Column('options_snapshot', sa.JSON()))
        b.add_column(sa.Column('stock_state', sa.String(12), nullable=False, server_default='deducted'))
        b.alter_column('price_at_purchase', existing_type=sa.Numeric(10, 2), type_=sa.Numeric(12, 2),
                       existing_nullable=False)
        b.alter_column('product_id', existing_type=sa.Integer(), nullable=True)
        b.create_foreign_key('fk_order_items_variant', 'product_variants', ['variant_id'], ['id'])
        b.create_index('ix_order_items_order_id', ['order_id'])

    # ---- B. data backfill (existing data is preserved and mapped to the new structures)
    bind.execute(sa.text("UPDATE categories SET path = '/' || id || '/', public_effective = visible"))
    bind.execute(sa.text("UPDATE products SET status = CASE WHEN is_active THEN 'published' ELSE 'draft' END, "
                         "options = '{}', updated_at = created_at, brand = ''"))
    bind.execute(sa.text(
        "INSERT INTO product_variants (product_id, sku, option_key, stock, reserved, is_active, position) "
        "SELECT id, 'P' || id, '', COALESCE(stock, 0), 0, 1, 0 FROM products"))
    bind.execute(sa.text(
        "INSERT INTO product_images (product_id, url, alt_text, position, is_primary) "
        "SELECT id, image_url, name, 0, 1 FROM products WHERE image_url IS NOT NULL AND image_url <> ''"))
    bind.execute(sa.text(
        "INSERT INTO product_categories (product_id, category_id) "
        "SELECT id, category_id FROM products WHERE category_id IS NOT NULL"))
    bind.execute(sa.text("UPDATE products SET min_price = price"))
    bind.execute(sa.text(
        "UPDATE cart_items SET variant_id = (SELECT v.id FROM product_variants v "
        "WHERE v.product_id = cart_items.product_id AND v.option_key = '')"))
    bind.execute(sa.text("UPDATE orders SET status = 'pending' WHERE status IS NULL"))
    bind.execute(sa.text("UPDATE orders SET status = 'preparing' WHERE status = 'processing'"))
    bind.execute(sa.text("UPDATE orders SET status = 'received' WHERE status = 'delivered'"))
    bind.execute(sa.text(
        "UPDATE orders SET subtotal = COALESCE(total_amount, 0), "
        "ship_name = (SELECT name FROM users u WHERE u.id = orders.user_id), "
        "ship_phone = (SELECT phone FROM users u WHERE u.id = orders.user_id), "
        "updated_at = created_at"))
    bind.execute(sa.text(
        "UPDATE order_items SET "
        "variant_id = (SELECT v.id FROM product_variants v WHERE v.product_id = order_items.product_id AND v.option_key = ''), "
        "product_name = COALESCE((SELECT p.name FROM products p WHERE p.id = order_items.product_id), ''), "
        "sku = COALESCE((SELECT v.sku FROM product_variants v WHERE v.product_id = order_items.product_id AND v.option_key = ''), ''), "
        "options_snapshot = '{}'"))
    # legacy checkout already deducted stock, so legacy items are 'deducted' (the column default)
    bind.execute(sa.text(
        "INSERT INTO order_status_history (order_id, from_status, to_status, note, created_at) "
        "SELECT id, NULL, status, 'migrated from legacy order', created_at FROM orders"))

    bind.execute(sa.text(
        "INSERT INTO store_settings (store_name, description, currency, locale, social_links) "
        "VALUES ('Raven', '', 'USD', 'en', '{}')"))
    bind.execute(sa.text(
        "INSERT INTO shipping_methods (code, name, description, price, is_active, position) "
        "VALUES ('standard', 'Standard shipping', '', 0, 1, 0)"))
    bind.execute(sa.text(
        "INSERT INTO homepage_sections (title, description, include_subcategories, product_limit, is_active, visible, position) "
        "VALUES ('New arrivals', '', 1, 10, 1, 1, 0)"))

    # ---- C. cleanup of superseded columns (data already copied above)
    with op.batch_alter_table('cart_items') as b:
        b.create_unique_constraint('uq_cart_user_variant', ['user_id', 'variant_id'])
    with op.batch_alter_table('orders') as b:
        b.alter_column('status', existing_type=sa.String(20), nullable=False)
        b.alter_column('total_amount', existing_type=sa.Numeric(10, 2), type_=sa.Numeric(12, 2),
                       existing_nullable=True)
    with op.batch_alter_table('users') as b:
        b.drop_index('ix_users_phone')
        b.create_index('ix_users_phone', ['phone'], unique=True)
    with op.batch_alter_table('products') as b:
        b.drop_column('stock')
        b.drop_column('image_url')
        b.drop_column('is_active')


def downgrade():
    # Destructive (variants, snapshots, payments would be lost); restore from backup instead.
    raise RuntimeError('Downgrade from 0002_upgrade is not supported; restore the pre-upgrade backup.')
