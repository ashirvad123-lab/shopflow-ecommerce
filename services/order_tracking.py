from datetime import datetime, timezone

from sqlalchemy import update

from extensions import db
from models import Order, OrderStatusHistory, Product


NEXT_STATUS = {
    'Order Placed': 'Confirmed',
    'Confirmed': 'Shipped',
    'Shipped': 'Delivered',
    'Delivered': None,
    'Cancelled': None,
}
CANCELLABLE_STATUSES = {'Order Placed', 'Confirmed', 'Pending'}


def allowed_order_statuses(status):
    next_status = NEXT_STATUS.get(status)
    choices = [next_status] if next_status else []
    if status in CANCELLABLE_STATUSES:
        choices.append('Cancelled')
    return choices


def transition_order(order, new_status, actor=None, note=None, tracking_number=None, courier_name=None):
    if new_status not in Order.STATUS_CHOICES:
        raise ValueError('Choose a valid order status.')
    if new_status not in allowed_order_statuses(order.status):
        raise ValueError(f'Cannot change order status from {order.status} to {new_status}.')

    claimed_transition = db.session.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == order.status)
        .values(status=new_status)
        .execution_options(synchronize_session=False)
    )
    if claimed_transition.rowcount != 1:
        raise ValueError('This order was updated by another request. Reload it and try again.')

    if new_status == 'Cancelled':
        if note and len(note) > 1000:
            raise ValueError('Cancellation reason must be 1000 characters or fewer.')
        for item in order.items:
            if item.product_id:
                db.session.execute(
                    update(Product)
                    .where(Product.id == item.product_id)
                    .values(stock=Product.stock + item.quantity)
                )
        order.cancelled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        order.cancellation_reason = note or None
        if order.payment_status in {'Paid', 'Succeeded', 'Completed'}:
            order.refund_status = 'Refund pending'
    elif new_status == 'Shipped':
        if tracking_number is not None:
            order.tracking_number = tracking_number.strip() or None
        if courier_name is not None:
            order.courier_name = courier_name.strip() or None

    order.status = new_status
    db.session.add(OrderStatusHistory(
        order=order,
        status=new_status,
        note=note,
        actor=actor,
        tracking_number=order.tracking_number,
        courier_name=order.courier_name,
    ))
    return order


def record_initial_order_status(order, actor=None):
    db.session.add(OrderStatusHistory(
        order=order,
        status=order.status,
        note='Order placed',
        actor=actor,
    ))
