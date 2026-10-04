import click
from flask.cli import with_appcontext
from .extensions import db
from .models import User, Category, Product


@click.command('init-db')
@with_appcontext
def init_db_command():
    db.create_all()
    click.echo('Database initialized.')


@click.command('seed')
@with_appcontext
def seed_command():
    db.create_all()

    if not User.query.filter_by(phone='09120000001').first():
        u = User(phone='09120000001', name='Admin', role='admin')
        u.set_password('admin123')
        db.session.add(u)

    if not User.query.filter_by(phone='09120000002').first():
        u = User(phone='09120000002', name='Staff', role='staff')
        u.set_password('staff123')
        db.session.add(u)

    if not User.query.filter_by(phone='09120000003').first():
        u = User(phone='09120000003', name='Customer', role='customer')
        u.set_password('customer123')
        db.session.add(u)

    if Category.query.count() == 0:
        db.session.add_all([
            Category(name='Electronics', slug='electronics'),
            Category(name='Books', slug='books'),
            Category(name='Clothing', slug='clothing'),
        ])
        db.session.commit()

    if Product.query.count() == 0:
        elec = Category.query.filter_by(slug='electronics').first()
        books = Category.query.filter_by(slug='books').first()
        db.session.add_all([
            Product(name='Wireless Headphones', slug='wireless-headphones', price=79.99, stock=25,
                    description='Comfortable over-ear headphones with great battery life.',
                    category_id=elec.id, image_url='https://picsum.photos/seed/headphones/500/350'),
            Product(name='Smart Watch', slug='smart-watch', price=149.50, stock=15,
                    description='Track fitness, notifications and more.',
                    category_id=elec.id, image_url='https://picsum.photos/seed/watch/500/350'),
            Product(name='Flask Web Development', slug='flask-web-development', price=29.99, stock=40,
                    description='Learn Flask from scratch with real projects.',
                    category_id=books.id, image_url='https://picsum.photos/seed/book/500/350'),
        ])

    db.session.commit()
    click.echo('Seed complete. Logins:')
    click.echo('  09120000001 / admin123')
    click.echo('  09120000002 / staff123')
    click.echo('  09120000003 / customer123')


def register_cli(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_command)