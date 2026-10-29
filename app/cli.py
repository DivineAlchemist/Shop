import click
from flask.cli import with_appcontext
from .extensions import db
from .models import (User, Category, Product, Tag, HomepageSection, Banner, StoreSettings, ShippingMethod,
                     ProductVariant, ProductImage)
from .utils import slugify


def _demo_catalog():
    from .services.catalog import rebuild_subtree
    from .services.products import save_product
    from werkzeug.datastructures import MultiDict

    def cat(name, parent=None, **kw):
        c = Category(name=name, slug=slugify(name), parent=parent, **kw)
        db.session.add(c)
        db.session.flush()
        rebuild_subtree(c)
        return c
    men = cat('Men')
    tops = cat('Tops', men)
    tees = cat('T-Shirts', tops)
    cat('Pants', men)
    women = cat('Women')
    cat('Dresses', women)
    cat('Accessories')
    featured = cat('Homepage Picks', is_internal=True, visible=False)  # internal merchandising group
    demo = [
        ('Classic T-Shirt', 'TSH-001', 20, '', tees, 'Color: Black, White\nSize: S, M, L', 'cotton, summer', 'Material: Cotton'),
        ('Linen Summer Dress', 'DRS-001', 45, 39, women, 'Size: S, M, L', 'linen, summer, sale', 'Material: Linen'),
        ('Wool Scarf', 'ACC-001', 18, '', Category.query.filter_by(slug='accessories').first(), '', 'wool, winter', 'Material: Wool'),
    ]
    for name, sku, price, sale, c, opts, tags, attrs in demo:
        form = MultiDict(dict(name=name, sku=sku, price=str(price), sale_price=str(sale), status='published', options=opts,
                              tags=tags, attributes=attrs, stock='20', category_id=str(c.id),
                              new_image_urls=f'https://picsum.photos/seed/{sku}/600/450'))
        form.add('category_ids', str(c.id))
        form.add('category_ids', str(featured.id))
        p, errs = save_product(None, form, MultiDict())
        assert not errs, errs
        for v in p.variants:
            v.stock = 20
        p.refresh_price_cache()
    db.session.add(HomepageSection(title='', source_category_id=featured.id, product_limit=10, position=0,
                                   auto_scroll=True, scroll_interval=5))


@click.command('init-db')
@with_appcontext
def init_db_command():
    """Create tables directly (tests/throwaway DBs only - use `flask db upgrade` for real databases)."""
    db.create_all()
    click.echo('Database initialized.')


@click.command('seed')
@with_appcontext
def seed_command():
    """Demo users + clothing catalog (idempotent; never deletes data)."""
    for phone, name, role, pw in (('09120000001', 'Admin', 'admin', 'admin123'),
                                  ('09120000002', 'Staff', 'staff', 'staff123'),
                                  ('09120000003', 'Customer', 'customer', 'customer123')):
        if not User.query.filter_by(phone=phone).first():
            u = User(phone=phone, name=name, role=role, phone_verified=True)
            u.set_password(pw)
            db.session.add(u)
    if StoreSettings.query.first() is None:
        db.session.add(StoreSettings(store_name='Raven', currency='USD', locale='en'))
    if ShippingMethod.query.count() == 0:
        db.session.add(ShippingMethod(code='standard', name='Standard shipping', price=0))
    db.session.commit()
    if Category.query.count() == 0 and Product.query.count() == 0:
        _demo_catalog()
        db.session.commit()
    click.echo('Seed complete. Logins:\n  09120000001 / admin123\n  09120000002 / staff123\n  09120000003 / customer123')


@click.command('expire-orders')
@with_appcontext
def expire_orders_command():
    """Fail unpaid online orders past their payment window and release reserved stock."""
    from .services.orders import expire_unpaid_orders
    click.echo(f'Expired {expire_unpaid_orders()} order(s).')


@click.command('reconcile-payments')
@with_appcontext
def reconcile_payments_command():
    """Re-verify payments whose callback was lost."""
    from .services.payments import reconcile_pending
    click.echo(f'Finalized {reconcile_pending()} payment(s).')


@click.command('sms-retry')
@with_appcontext
def sms_retry_command():
    """Retry failed (non-OTP) SMS messages."""
    from .services.sms import retry_failed
    click.echo(f'Recovered {retry_failed()} message(s).')


@click.command('send-marketing')
@click.argument('campaign_id')
@click.argument('message')
@with_appcontext
def send_marketing_command(campaign_id, message):
    """Send a promotional SMS to consenting customers (idempotent per campaign id)."""
    from flask import current_app
    from .services.notifications import send_marketing
    with current_app.test_request_context(base_url=current_app.config.get('SITE_URL') or 'http://localhost'):
        click.echo(f'Sent {send_marketing(message, campaign_id)} message(s).')


def register_cli(app):
    for c in (init_db_command, seed_command, expire_orders_command, reconcile_payments_command,
              sms_retry_command, send_marketing_command):
        app.cli.add_command(c)
