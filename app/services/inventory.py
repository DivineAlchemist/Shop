"""Variant stock bookkeeping with atomic conditional UPDATEs (safe under concurrent checkouts).

Lifecycle per order item (`OrderItem.stock_state`):
    reserved --commit--> deducted --restore--> restored
    reserved --release--> released
Each transition is a compare-and-set on the item's state, so repeating an operation is a no-op.
"""
from sqlalchemy import update
from ..extensions import db
from ..models import ProductVariant, OrderItem


class InsufficientStock(Exception):
    def __init__(self, name=''):
        super().__init__(f'Not enough stock for {name}'.strip())
        self.name = name


def reserve(variant_id, qty, name=''):
    res = db.session.execute(update(ProductVariant).where(
        ProductVariant.id == variant_id, ProductVariant.is_active.is_(True),
        ProductVariant.stock - ProductVariant.reserved >= qty
    ).values(reserved=ProductVariant.reserved + qty))
    if res.rowcount != 1:
        raise InsufficientStock(name)


def _cas_state(item, old, new):
    res = db.session.execute(update(OrderItem).where(
        OrderItem.id == item.id, OrderItem.stock_state == old).values(stock_state=new))
    return res.rowcount == 1


def commit_item(item):
    """reserved -> deducted (stock decreases, reservation released)."""
    if not item.variant_id or not _cas_state(item, 'reserved', 'deducted'):
        return False
    res = db.session.execute(update(ProductVariant).where(
        ProductVariant.id == item.variant_id, ProductVariant.reserved >= item.quantity,
        ProductVariant.stock >= item.quantity
    ).values(stock=ProductVariant.stock - item.quantity, reserved=ProductVariant.reserved - item.quantity))
    if res.rowcount != 1:
        raise RuntimeError(f'Inventory inconsistency for variant {item.variant_id}')
    return True


def release_item(item):
    """reserved -> released."""
    if not item.variant_id or not _cas_state(item, 'reserved', 'released'):
        return False
    db.session.execute(update(ProductVariant).where(
        ProductVariant.id == item.variant_id, ProductVariant.reserved >= item.quantity
    ).values(reserved=ProductVariant.reserved - item.quantity))
    return True


def restore_item(item):
    """deducted -> restored (units go back on the shelf)."""
    if not item.variant_id or not _cas_state(item, 'deducted', 'restored'):
        return False
    db.session.execute(update(ProductVariant).where(ProductVariant.id == item.variant_id)
                       .values(stock=ProductVariant.stock + item.quantity))
    return True


def commit_order(order):
    return [commit_item(i) for i in order.items]


def undo_order(order):
    """Cancel/failed: release what is still reserved and restore what was already deducted."""
    for i in order.items:
        release_item(i)
        restore_item(i)


def re_reserve_order(order):
    """Used to revive an expired order that was paid late. All-or-nothing; returns bool."""
    done = []
    try:
        for i in sorted(order.items, key=lambda x: x.variant_id or 0):
            if i.stock_state != 'released' or not i.variant_id:
                raise InsufficientStock(i.product_name)
            reserve(i.variant_id, i.quantity, i.product_name)
            done.append(i)
    except InsufficientStock:
        for i in done:  # undo partial reservations
            db.session.execute(update(ProductVariant).where(ProductVariant.id == i.variant_id)
                               .values(reserved=ProductVariant.reserved - i.quantity))
        return False
    for i in done:
        _cas_state(i, 'released', 'reserved')
    return True
