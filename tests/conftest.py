import os
os.environ['APP_ENV'] = 'testing'
import pytest
from werkzeug.datastructures import MultiDict

from app import create_app
from app.extensions import db
from app.models import User, Category, StoreSettings, ShippingMethod
from app.services.catalog import rebuild_subtree
from app.services.products import save_product
from app.services.sms.mock import MockProvider
from app.services.payments.mock import MockGateway


@pytest.fixture()
def app():
    MockProvider.reset()
    MockGateway.reset()
    app = create_app()
    app.config.update(SMS_RETRY_BACKOFF=0, OTP_RESEND_COOLDOWN=0)

    @app.teardown_request
    def _forget_cached_user(exc):
        # the fixture keeps one app context open; real requests get a fresh `g`
        from flask import g
        g.pop('_login_user', None)
        g.pop('_store_settings', None)
        g.pop('_locale', None)
    with app.app_context():
        db.create_all()
        db.session.add(StoreSettings(store_name='Test', currency='IRT', locale='en'))
        db.session.add(ShippingMethod(code='standard', name='Standard', price=10))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(phone='09120000009', role='customer', password='password1', name='U'):
    u = User(phone=phone, name=name, role=role, phone_verified=True)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def login(client, user, password='password1'):
    return client.post('/auth/login', data={'phone': user.phone, 'password': password}, follow_redirects=False)


def make_cat(name, parent=None, **kw):
    c = Category(name=name, slug=name.lower().replace(' ', '-'), parent=parent, **kw)
    db.session.add(c)
    db.session.flush()
    rebuild_subtree(c)
    db.session.commit()
    return c


def make_product(name='Shirt', price='100', cats=(), stock=5, options='', status='published', **extra):
    form = MultiDict(dict(name=name, price=str(price), status=status, options=options, stock=str(stock), **extra))
    for c in cats:
        form.add('category_ids', str(c.id))
    if cats:
        form['category_id'] = str(cats[0].id)
    p, errs = save_product(None, form, MultiDict())
    assert not errs, errs
    db.session.commit()
    return p
