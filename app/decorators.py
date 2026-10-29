from functools import wraps
from flask import abort
from flask_login import current_user

# Role -> permission map. Staff run the catalog/orders/settings; admin additionally manages users and refunds.
STAFF_PERMISSIONS = {'catalog', 'orders', 'settings', 'coupons', 'marketing'}
ROLE_PERMISSIONS = {
    'staff': STAFF_PERMISSIONS,
    'admin': STAFF_PERMISSIONS | {'users', 'refunds'},
}


def has_permission(user, perm):
    return bool(user.is_authenticated and perm in ROLE_PERMISSIONS.get(user.role, ()))


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def permission_required(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not has_permission(current_user, perm):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


staff_required = role_required('staff', 'admin')
admin_required = role_required('admin')
