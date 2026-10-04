import os
from flask import Flask, render_template
from .extensions import db, migrate, login_manager, bcrypt
from .models import User


def create_app(config_object='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_object)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Blueprints
    from .auth import auth_bp
    from .customer import customer_bp
    from .staff import staff_bp
    from .admin import admin_bp
    from .admin.routes import init_admin
    from .cli import register_cli

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(customer_bp)
    app.register_blueprint(staff_bp, url_prefix='/staff')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    init_admin(app)
    register_cli(app)

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

    return app