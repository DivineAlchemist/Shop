from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from sqlalchemy import func
from ..models import User, Product, Category, Order, OrderItem, Tag, Banner, HomepageSection, Coupon, StoreSettings
from ..extensions import db
from ..decorators import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.status.notin_(('cancelled', 'failed'))).scalar()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template('panel/dashboard.html',
                           total_users=total_users,
                           total_products=total_products,
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           revenue=revenue,
                           recent_orders=recent_orders)


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('panel/users.html', users=all_users)


@admin_bp.route('/users/<int:user_id>/role', methods=['POST'])
@login_required
@admin_required
def set_role(user_id):
    user = User.query.get_or_404(user_id)
    role = request.form.get('role')
    if role in ('customer', 'staff', 'admin'):
        if user.id == current_user.id and role != 'admin':
            flash("You can't demote yourself.", 'danger')
        else:
            user.role = role
            db.session.commit()
            flash(f'Role updated to {role}.', 'success')
    return redirect(url_for('admin.users'))


# ---------- Flask-Admin panel (mounted at /admin-panel) ----------

class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == 'admin'

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login', next=request.url))


class SecureIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == 'admin'

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login', next=request.url))



class UserAdminView(SecureModelView):
    column_exclude_list = ['password_hash']
    form_excluded_columns = ['password_hash', 'cart_items', 'orders', 'addresses', 'failed_logins']
    column_searchable_list = ['phone', 'name']
    can_create = False
    can_delete = True


class OrderAdminView(SecureModelView):
    column_default_sort = ('created_at', True)
    can_create = can_edit = can_delete = False  # orders change only through the audited workflow


class ReadOnlyView(SecureModelView):
    """Catalog/order data has invariants (paths, stock, snapshots) that only the staff panel maintains."""
    can_create = can_edit = can_delete = False


def init_admin(app):
    admin = Admin(
        app,
        name='Shop Admin',
        url='/admin-panel',
        endpoint='flaskadmin',          # <-- unique endpoint for Flask-Admin's index
        index_view=SecureIndexView(url='/admin-panel', endpoint='flaskadmin'),  # <-- match it here too
        template_mode='bootstrap4'
    )
    admin.add_view(UserAdminView(User, db.session, category='Users', endpoint='admin_users'))
    admin.add_view(ReadOnlyView(Category, db.session, category='Catalog', endpoint='admin_categories'))
    admin.add_view(ReadOnlyView(Product, db.session, category='Catalog', endpoint='admin_products'))
    admin.add_view(SecureModelView(Tag, db.session, category='Catalog', endpoint='admin_tags'))
    admin.add_view(SecureModelView(Banner, db.session, category='Storefront', endpoint='admin_banners'))
    admin.add_view(SecureModelView(HomepageSection, db.session, category='Storefront', endpoint='admin_sections'))
    admin.add_view(SecureModelView(Coupon, db.session, category='Sales', endpoint='admin_coupons'))
    admin.add_view(OrderAdminView(Order, db.session, category='Sales', endpoint='admin_orders'))
    admin.add_view(ReadOnlyView(OrderItem, db.session, category='Sales', endpoint='admin_orderitems'))