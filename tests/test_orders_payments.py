from datetime import datetime, timedelta
from unittest import mock
import pytest
from app.extensions import db
from app.models import Order, CartItem, ProductVariant, Coupon, Payment, SmsLog
from app.services import orders as osvc, inventory, payments, pricing
from app.services.payments.mock import MockGateway
from app.services.payments.zarinpal import ZarinpalGateway
from app.services.sms.mock import MockProvider
from .conftest import make_user, make_product, make_cat, login

ADDR = dict(name='Ali', phone='09121111111', city='Tehran', address_line='Valiasr 1', postal_code='123')


def add_cart(user, product, variant=None, qty=1):
    v = variant or product.variants[0]
    db.session.add(CartItem(user_id=user.id, product_id=product.id, variant_id=v.id, quantity=qty))
    db.session.commit()
    return v


def place(user, method='cod', coupon=None):
    order, err = osvc.create_order(user, ADDR, 'standard', coupon, method)
    assert err is None, err
    return order


def test_variant_stock_snapshot_and_cod_flow(app):
    u = make_user(); p = make_product('Tee', 100, options='Color: Blue, Black\nSize: M, L', stock=0)
    blue_m = next(v for v in p.variants if v.options_labels == {'Color': 'Blue', 'Size': 'M'})
    blue_m.stock = 3; blue_m.sku = 'TEE-BM'; db.session.commit()
    add_cart(u, p, blue_m, 2)
    order = place(u)
    item = order.items[0]
    assert (item.product_name, item.sku, item.variant_label) == ('Tee', 'TEE-BM', 'Blue / M')
    assert item.options_snapshot == {'Color': 'Blue', 'Size': 'M'} and item.quantity == 2
    db.session.refresh(blue_m)
    assert (blue_m.stock, blue_m.reserved) == (3, 2)           # reserved, not deducted yet
    assert CartItem.query.count() == 0
    # snapshot is immutable: renaming the product does not change the order
    p.name = 'Renamed'; db.session.commit()
    assert order.items[0].product_name == 'Tee'
    staff = make_user('09120000002', 'staff')
    osvc.transition_order(order, 'preparing', staff)
    db.session.refresh(blue_m)
    assert (blue_m.stock, blue_m.reserved) == (1, 0)           # COD: deducted on acceptance, exactly once
    with pytest.raises(osvc.InvalidTransition):
        osvc.transition_order(order, 'shipped', staff)         # needs provider + tracking
    osvc.transition_order(order, 'shipped', staff, provider='Post', tracking='TRK1')
    with pytest.raises(osvc.InvalidTransition):
        osvc.transition_order(order, 'shipped', staff, provider='Post', tracking='TRK1')  # repeat is rejected
    with pytest.raises(osvc.InvalidTransition):
        osvc.transition_order(order, 'cancelled', staff)       # no cancel once shipped
    osvc.customer_confirm_received(order, u)
    assert order.status == 'received' and order.payment_status == 'paid'
    assert [h.to_status for h in order.history] == ['pending', 'preparing', 'shipped', 'received']
    assert order.history[1].changed_by_id == staff.id
    sent = [t for _, t in MockProvider.outbox]
    assert any('TRK1' in t for t in sent) and sum('received' in t or 'delivery' in t for t in sent) == 1


def test_cancel_restores_stock_once_and_ownership(app):
    u = make_user(); other = make_user('09120000008'); p = make_product('Cap', 20, stock=4)
    add_cart(u, p, qty=3)
    order = place(u)
    with pytest.raises(osvc.InvalidTransition):
        osvc.customer_cancel(order, other)
    osvc.customer_cancel(order, u)
    v = p.variants[0]; db.session.refresh(v)
    assert (v.stock, v.reserved) == (4, 0)
    with pytest.raises(osvc.InvalidTransition):
        osvc.customer_cancel(order, u)
    # cancelling after staff accepted restores deducted stock
    add_cart(u, p, qty=2); o2 = place(u)
    staff = make_user('09120000002', 'staff'); osvc.transition_order(o2, 'preparing', staff)
    db.session.refresh(v); assert v.stock == 2
    osvc.transition_order(o2, 'cancelled', staff)
    db.session.refresh(v); assert (v.stock, v.reserved) == (4, 0)


def test_no_oversell_and_cart_validation(app):
    a = make_user(); b = make_user('09120000008'); p = make_product('Last', 50, stock=1)
    add_cart(a, p); add_cart(b, p)
    place(a)
    order, err = osvc.create_order(b, ADDR, 'standard', None, 'cod')
    assert order is None and 'stock' in err.lower()
    assert Order.query.count() == 1 and p.variants[0].reserved == 1 and CartItem.query.count() == 1
    with pytest.raises(inventory.InsufficientStock):
        inventory.reserve(p.variants[0].id, 1)


def test_coupon_and_totals(app):
    u = make_user(); p = make_product('Hat', 100, stock=10)
    db.session.add(Coupon(code='SAVE10', kind='percent', value=10, usage_limit=1, min_subtotal=50)); db.session.commit()
    add_cart(u, p, qty=2)
    q = pricing.quote(u, 'standard', 'save10')
    assert (str(q.subtotal), str(q.discount), str(q.shipping), str(q.total)) == ('200.00', '20.00', '10.00', '190.00')
    assert pricing.quote(u, 'standard', 'NOPE').coupon_error
    order = place(u, coupon='SAVE10')
    assert order.coupon_code == 'SAVE10' and str(order.total_amount) == '190.00'
    add_cart(u, p, qty=1)
    assert pricing.quote(u, 'standard', 'SAVE10').coupon_error                  # usage limit reached
    osvc.customer_cancel(order, u)
    assert Coupon.query.first().used_count == 0                                  # released on cancel


def pay_flow(client, user, order, result='pay'):
    login(client, user)
    r = client.post(f'/orders/{order.id}/pay')
    assert r.status_code == 302
    auth = Payment.query.filter_by(order_id=order.id).order_by(Payment.id.desc()).first().authority
    r = client.post(f'/payment/mock/{auth}', data={'result': result})
    return auth, r


def test_online_payment_verify_duplicate_callback(app, client):
    u = make_user(); p = make_product('Bag', 1000, stock=2)
    add_cart(u, p, qty=2); order = place(u, 'online')
    assert order.payment_status == 'unpaid' and p.variants[0].reserved == 2
    auth, r = pay_flow(client, u, order)
    assert 'Status=OK' in r.headers['Location']
    client.get(r.headers['Location'])
    client.get(r.headers['Location'])                                           # duplicate callback
    db.session.expire_all()
    v = p.variants[0]; order = db.session.get(Order, order.id)
    assert order.payment_status == 'paid' and (v.stock, v.reserved) == (0, 0)  # deducted exactly once
    pay = Payment.query.one()
    assert pay.status == 'paid' and pay.ref_id and pay.gateway_amount == 2010 * 10  # IRT -> Rial, incl. shipping
    # a forged "OK" for an unpaid authority is NOT trusted: verification happens server-side
    add_cart(u, p, qty=0 or 1) if False else None


def test_forged_callback_and_cancel_and_retry(app, client):
    u = make_user(); p = make_product('Bag', 1000, stock=3)
    add_cart(u, p); order = place(u, 'online')
    login(client, u); client.post(f'/orders/{order.id}/pay')
    auth = Payment.query.first().authority
    client.get(f'/payment/callback?Authority={auth}&Status=OK')                # user never paid at the bank
    db.session.expire_all()
    assert db.session.get(Order, order.id).payment_status == 'unpaid' and Payment.query.first().status == 'failed'
    client.get('/payment/callback?Authority=BOGUS&Status=OK')                  # unknown authority is harmless
    auth2, r = pay_flow(client, u, order)                                       # retry succeeds
    client.get(r.headers['Location'])
    db.session.expire_all()
    assert db.session.get(Order, order.id).payment_status == 'paid' and Payment.query.count() == 2


def test_gateway_network_error_keeps_payment_retryable(app, client):
    u = make_user(); p = make_product('Bag', 1000, stock=3)
    add_cart(u, p); order = place(u, 'online')
    auth, r = pay_flow(client, u, order)
    MockGateway.fail_verify_network = True
    client.get(r.headers['Location'])
    db.session.expire_all(); assert Payment.query.first().status == 'pending'
    assert db.session.get(Order, order.id).payment_status == 'unpaid'
    MockGateway.fail_verify_network = False
    assert payments.reconcile_pending(older_than_minutes=-1) == 1
    db.session.expire_all(); assert db.session.get(Order, order.id).payment_status == 'paid'


def test_expiry_releases_stock_and_late_payment_revives(app, client):
    u = make_user(); p = make_product('Bag', 1000, stock=1)
    add_cart(u, p); order = place(u, 'online')
    auth, r = pay_flow(client, u, order)
    order.reserved_until = datetime.utcnow() - timedelta(minutes=1); db.session.commit()
    # payment in flight blocks expiry only while 'verifying'; here it is pending -> order expires
    assert osvc.expire_unpaid_orders() == 1
    db.session.expire_all(); o = db.session.get(Order, order.id); v = p.variants[0]
    assert o.status == 'failed' and (v.stock, v.reserved) == (1, 0)
    client.get(r.headers['Location'])                                           # customer paid after expiry
    db.session.expire_all(); o = db.session.get(Order, order.id)
    assert o.status == 'pending' and o.payment_status == 'paid' and p.variants[0].stock == 0   # revived
    # same, but stock was taken by someone else -> paid order is flagged for refund
    add_cart(u, make_product('Tee', 10, stock=1)); o2 = place(u, 'online')
    a2, r2 = pay_flow(client, u, o2)
    o2.reserved_until = datetime.utcnow() - timedelta(minutes=1); db.session.commit(); osvc.expire_unpaid_orders()
    v2 = o2.items[0].variant; v2.stock = 0; db.session.commit()
    client.get(r2.headers['Location'])
    db.session.expire_all(); o2 = db.session.get(Order, o2.id)
    assert o2.status == 'failed' and o2.payment_status == 'paid' and any('Refund' in h.note for h in o2.history)
    admin = make_user('09120000001', 'admin'); osvc.mark_refunded(o2, admin); assert o2.payment_status == 'refunded'


def test_online_order_cannot_be_prepared_unpaid(app):
    u = make_user(); p = make_product('Bag', 1000, stock=1); add_cart(u, p); order = place(u, 'online')
    with pytest.raises(osvc.InvalidTransition):
        osvc.transition_order(order, 'preparing', make_user('09120000002', 'staff'))


def test_zarinpal_adapter_request_and_verify_with_mocked_http(app):
    app.config['TESTING'] = False                                                # real adapter refuses to run in tests
    gw = ZarinpalGateway('merchant-uuid', sandbox=True)
    ok_req = mock.Mock(status_code=200, json=lambda: {'data': {'code': 100, 'authority': 'A0001'}, 'errors': []})
    with mock.patch('requests.post', return_value=ok_req) as post:
        init = gw.request(20000, 'https://x/cb', 'Order #1', mobile='0912')
    url, kw = post.call_args[0][0], post.call_args[1]
    assert url == 'https://sandbox.zarinpal.com/pg/v4/payment/request.json'
    assert kw['json']['amount'] == 20000 and kw['json']['merchant_id'] == 'merchant-uuid'
    assert init.ok and init.redirect_url == 'https://sandbox.zarinpal.com/pg/StartPay/A0001'
    bad = mock.Mock(status_code=200, json=lambda: {'data': [], 'errors': {'code': -9, 'message': 'validation'}})
    with mock.patch('requests.post', return_value=bad):
        assert gw.request(1, 'u', 'd').error_code == '-9'
    v100 = mock.Mock(status_code=200, json=lambda: {'data': {'code': 100, 'ref_id': 77, 'card_pan': '6037'}, 'errors': []})
    v101 = mock.Mock(status_code=200, json=lambda: {'data': {'code': 101, 'ref_id': 77}, 'errors': []})
    with mock.patch('requests.post', return_value=v100) as post:
        r = gw.verify('A0001', 20000)
    assert post.call_args[0][0].endswith('/pg/v4/payment/verify.json') and r.ok and r.ref_id == '77' and not r.already_verified
    with mock.patch('requests.post', return_value=v101):
        assert gw.verify('A0001', 20000).already_verified
    import requests
    with mock.patch('requests.post', side_effect=requests.ConnectionError('boom')):
        res = gw.verify('A0001', 20000)
    assert not res.ok and res.retryable
    with mock.patch('app.services.payments.zarinpal.current_app') as ca:
        ca.config = {'TESTING': True}
        with pytest.raises(RuntimeError):
            ZarinpalGateway('m')
