import logging
import os
from datetime import datetime
from decimal import Decimal
from flask import Flask, render_template, send_from_directory, g, request, url_for
from flask_login import current_user
from .extensions import db, migrate, login_manager, bcrypt, csrf
from .models import User, StoreSettings


def _configure_logging(app):
    level = logging.DEBUG if app.debug else logging.INFO
    if not app.testing and not logging.getLogger().handlers:
        logging.basicConfig(level=level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app.logger.setLevel(level)


def format_money(value, currency=None):
    try:
        d = Decimal(str(value))
    except Exception:
        return value
    cur = currency
    if cur is None:
        s = get_settings()
        cur = s.currency if s else 'USD'
    if cur == 'USD':
        return f'${d:,.2f}'
    if cur in ('IRT', 'IRR'):
        from .i18n import current_locale
        fa = current_locale() == 'fa'
        return f'{int(d):,} {("تومان" if fa else "Toman") if cur == "IRT" else ("ریال" if fa else "Rial")}'
    return f'{d:,.2f} {cur}'


def get_settings():
    """Single settings row, cached for the request."""
    if not hasattr(g, '_store_settings'):
        try:
            g._store_settings = StoreSettings.query.first()
        except Exception:  # e.g. before migrations have run
            db.session.rollback()
            g._store_settings = None
    return g._store_settings


def _fix_sqlite_transactions(app):
    """pysqlite emits BEGIN lazily, which breaks SAVEPOINT/rollback semantics (a 'dry run' could commit).
    Standard SQLAlchemy recipe: take over BEGIN so nested transactions behave like on other databases."""
    from sqlalchemy import event
    with app.app_context():
        engine = db.engine
    if engine.dialect.name != 'sqlite':
        return

    @event.listens_for(engine, 'connect')
    def _connect(dbapi_connection, record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, 'begin')
    def _begin(conn):
        conn.exec_driver_sql('BEGIN')


def create_app(config_object=None):
    from config import get_config
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())
    if config_object is None and hasattr(get_config(), 'validate'):
        get_config().validate()  # production refuses to start with unsafe/missing settings

    _configure_logging(app)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    _fix_sqlite_transactions(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Blueprints
    from .auth import auth_bp
    from .customer import customer_bp
    from .staff import staff_bp
    from .admin import admin_bp
    from .payment import payment_bp
    from .admin.routes import init_admin
    from .cli import register_cli

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(customer_bp)
    app.register_blueprint(staff_bp, url_prefix='/staff')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(payment_bp)

    init_admin(app)
    register_cli(app)

    @app.route('/media/<path:path>')
    def media(path):
        return send_from_directory(app.config['UPLOAD_FOLDER'], path, max_age=3600)

    app.jinja_env.filters['money'] = format_money
    from .i18n import gettext
    app.jinja_env.globals['_'] = gettext
    app.jinja_env.tests['startswith'] = lambda value, prefix: str(value).startswith(prefix)

    @app.context_processor
    def inject_globals():
        from .services.catalog import category_tree
        from .decorators import has_permission
        nav = []
        if request.endpoint and not request.endpoint.startswith(('static', 'media')):
            try:
                nav = category_tree(public_only=True)
            except Exception:
                nav = []
        def page_url(n):
            args = {k: list(v) for k, v in request.args.lists() if k != 'page'}
            return url_for(request.endpoint, **(request.view_args or {}), **args, page=n)
        from .i18n import current_locale, text_dir
        return dict(locale=current_locale(), text_dir=text_dir(), store=get_settings(), nav_tree=nav, page_url=page_url, now_year=datetime.utcnow().year, can=lambda p: has_permission(current_user, p))

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        return resp

    # Error handlers
    @app.errorhandler(401)
    def unauthorized(e):
        return render_template('errors/401.html'), 401

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template('errors/404.html'), 413

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        app.logger.exception('Unhandled error')
        return render_template('errors/500.html'), 500

    return app
