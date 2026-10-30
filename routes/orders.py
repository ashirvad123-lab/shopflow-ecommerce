from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape
from io import BytesIO

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from extensions import db
from models import Order
from services.order_tracking import transition_order

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')


def _owned_order(order_id):
    order = db.get_or_404(Order, order_id)
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return order


@orders_bp.route('/')
@login_required
def history():
    query = Order.query.filter_by(user_id=current_user.id)
    status_filter = request.args.get('status', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    if status_filter in Order.STATUS_CHOICES:
        query = query.filter_by(status=status_filter)
    else:
        status_filter = ''
    try:
        if start_date:
            query = query.filter(Order.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(Order.created_at < datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
    except ValueError:
        flash('Use valid dates in YYYY-MM-DD format.', 'warning')
        start_date = ''
        end_date = ''

    page = query.order_by(Order.created_at.desc()).paginate(
        page=request.args.get('page', 1, type=int), per_page=10, error_out=False
    )
    return render_template(
        'orders/history.html',
        orders=page.items,
        pagination=page,
        has_any_orders=Order.query.filter_by(user_id=current_user.id).first() is not None,
        statuses=Order.STATUS_CHOICES,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date,
    )


@orders_bp.route('/<int:order_id>')
@login_required
def detail(order_id):
    order = _owned_order(order_id)
    step_map = {'Order Placed': 1, 'Pending': 1, 'Confirmed': 2, 'Shipped': 3, 'Delivered': 4, 'Cancelled': -1}
    return render_template(
        'orders/detail.html',
        order=order,
        current_step=step_map.get(order.status, 1),
    )


@orders_bp.route('/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    order = _owned_order(order_id)
    reason = request.form.get('reason', '').strip()
    try:
        transition_order(order, 'Cancelled', actor=current_user, note=reason)
        db.session.commit()
        flash(
            f'Order #{order.order_number} has been cancelled and inventory restored.'
            + (' A refund is pending confirmation.' if order.refund_status == 'Refund pending' else ''),
            'success',
        )
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'warning')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to cancel order %s', order.order_number)
        flash('The order could not be cancelled. Please try again.', 'danger')
    return redirect(url_for('orders.detail', order_id=order.id))


@orders_bp.route('/<int:order_id>/invoice')
@login_required
def invoice(order_id):
    order = _owned_order(order_id)
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=letter, rightMargin=0.65 * inch, leftMargin=0.65 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f'Invoice {order.order_number}', author=current_app.config['STORE_NAME'],
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='InvoiceRight', parent=styles['Normal'], alignment=TA_RIGHT))
    story = [
        Paragraph(escape(current_app.config['STORE_NAME']), styles['Title']),
        Paragraph(escape(current_app.config.get('STORE_ADDRESS', '') or ''), styles['Normal']),
        Paragraph(escape(current_app.config.get('STORE_EMAIL', '') or ''), styles['Normal']),
        Paragraph(escape(current_app.config.get('STORE_PHONE', '') or ''), styles['Normal']),
        Spacer(1, 18),
        Paragraph('INVOICE', styles['Heading1']),
        Paragraph(f'Invoice number: {escape(order.order_number)}', styles['Normal']),
        Paragraph(f'Order ID: {escape(order.order_number)}', styles['Normal']),
        Paragraph(f'Invoice date: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}', styles['Normal']),
        Spacer(1, 12),
        Paragraph('<b>Bill to</b>', styles['Heading3']),
        Paragraph(escape(order.full_name), styles['Normal']),
        Paragraph(escape(order.email), styles['Normal']),
        Paragraph(escape(order.phone), styles['Normal']),
        Paragraph(
            escape(f'{order.shipping_address}, {order.city}, {order.postal_code}'),
            styles['Normal'],
        ),
        Spacer(1, 18),
    ]
    currency = current_app.config.get('CURRENCY_SYMBOL', '$')
    rows = [['Description', 'Qty', 'Unit price', 'Line total']]
    for item in order.items:
        rows.append([
            Paragraph(escape(item.product_name), styles['Normal']),
            str(item.quantity),
            f'{currency}{Decimal(str(item.price)):,.2f}',
            f'{currency}{Decimal(str(item.subtotal)):,.2f}',
        ])
    rows.extend([
        ['', '', 'Product subtotal', f'{currency}{Decimal(str(order.subtotal)):,.2f}'],
        ['', '', 'Discount', f'-{currency}{Decimal(str(order.discount_amount or 0)):,.2f}'],
        ['', '', 'Delivery', f'{currency}{Decimal(str(order.shipping_fee)):,.2f}'],
        ['', '', 'Total', f'{currency}{Decimal(str(order.total_amount)):,.2f}'],
    ])
    table = Table(rows, colWidths=[3.45 * inch, 0.55 * inch, 1.15 * inch, 1.25 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f5eff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d9dee8')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        table,
        Spacer(1, 14),
        Paragraph(
            f'Payment method: {escape(order.payment_method)} &nbsp; | &nbsp; '
            f'Payment status: {escape(order.payment_status)}',
            styles['Normal'],
        ),
        Paragraph('Tax/GST is not charged because no tax configuration is set.', styles['Normal']),
    ])
    document.build(story)
    output.seek(0)
    response = send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'invoice-{order.order_number}.pdf',
    )
    response.headers['Cache-Control'] = 'private, no-store'
    return response
