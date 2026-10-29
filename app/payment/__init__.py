from flask import Blueprint

payment_bp = Blueprint('payment', __name__)

from . import routes  # noqa: E402,F401
