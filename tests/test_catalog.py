from datetime import datetime, timedelta
from app.extensions import db
from app.models import Category, HomepageSection, Banner, Product
from app.services import catalog as svc
from app.services.catalog import CatalogFilters
from .conftest import make_cat, make_product, make_user, login


def test_category_tree_cycle_and_depth(app):
    a = make_cat('A'); b = make_cat('B', a); c = make_cat('C', b)
    assert c.path == f'/{a.id}/{b.id}/{c.id}/' and c.depth == 2
    parent, err = svc.validate_parent(a, c.id)          # moving A under its own descendant
    assert err and parent is None
    assert svc.validate_parent(a, a.id)[1]
    assert svc.validate_parent(c, a.id)[1] is None
    c.parent = a; svc.rebuild_subtree(c); db.session.commit()
    assert c.depth == 1


def test_descendant_filtering_and_public_visibility(app):
    men = make_cat('Men'); tops = make_cat('Tops', men); tees = make_cat('Tees', tops)
    internal = make_cat('Picks', is_internal=True)
    hidden_parent = make_cat('Hidden', visible=False); child = make_cat('Child', hidden_parent)
    assert child.public_effective is False            # hidden parent hides the subtree
    p1 = make_product('Tee', cats=[tees]); p2 = make_product('Top', cats=[tops])
    p3 = make_product('Secret', cats=[internal]); p4 = make_product('InChild', cats=[child])
    p5 = make_product('Both', cats=[tees, internal]); p6 = make_product('Draft', cats=[tees], status='draft')
    names = lambda f: {p.name for p in svc.search_products(f).items}
    assert names(CatalogFilters(category=men)) == {'Tee', 'Top', 'Both'}      # includes descendants, no leaks
    assert names(CatalogFilters()) == {'Tee', 'Top', 'Both'}
    assert names(CatalogFilters(q='secret')) == set()
    assert svc.get_category(slug='picks') is None and svc.get_category(slug='picks', allow_internal=True)
    assert svc.product_by_slug(p3.slug) is None and svc.product_by_slug(p3.slug, True)
    assert svc.product_by_slug(p6.slug) is None
    assert client_get_status(app, f'/category/{internal.slug}') == 404
    assert client_get_status(app, f'/product/{p4.slug}') == 404


def client_get_status(app, url):
    return app.test_client().get(url).status_code


def test_search_filters_sort_pagination(app):
    cat = make_cat('Clothes')
    make_product('Red Cotton Shirt', 50, [cat], options='Color: Red, Blue\nSize: M, L', sku='SH-1', brand='Acme',
                 tags='summer, cotton', attributes='Material: Cotton', description='light fabric')
    make_product('Blue Wool Coat', 200, [cat], sku='CO-1', tags='winter, wool', attributes='Material: Wool')
    for i in range(14):
        make_product(f'Filler {i}', 10 + i, [cat], tags='filler')
    f = lambda **kw: {p.name for p in svc.search_products(CatalogFilters(per_page=50, **kw)).items}
    assert f(q='cotton') == {'Red Cotton Shirt'}              # name + tag + attribute
    assert f(q='SH-1') == {'Red Cotton Shirt'} and f(q='acme') == {'Red Cotton Shirt'}
    assert f(q='fabric') == {'Red Cotton Shirt'}
    assert f(tags=['summer', 'cotton']) == {'Red Cotton Shirt'}
    assert f(tags=['summer', 'wool']) == set()                # AND across tags
    assert f(attrs={'material': ['wool']}) == {'Blue Wool Coat'}
    assert f(options={'Color': ['color_red'], 'Size': ['size_l']}) == {'Red Cotton Shirt'}
    assert f(min_price=100) == {'Blue Wool Coat'} and f(category=cat, q='coat', max_price=300) == {'Blue Wool Coat'}
    assert f(q='100%') == set() and f(q='%') == set()           # LIKE wildcards are escaped
    pg = svc.search_products(CatalogFilters(per_page=5, sort='price_desc'))
    assert pg.pages == 4 and pg.items[0].name == 'Blue Wool Coat' and pg.total == 16
    asc = svc.search_products(CatalogFilters(per_page=3, sort='price_asc')).items
    assert [p.min_price for p in asc] == sorted(p.min_price for p in asc)
    fc = svc.facets(CatalogFilters(category=cat))
    assert ('summer' in [t[0] for t in fc['tags']]) and 'Color' in fc['options']


def test_homepage_sections_limit_order_and_internal_source(app):
    internal = make_cat('Picks', is_internal=True); pub = make_cat('Shirts')
    base = datetime.utcnow()
    for i in range(12):
        p = make_product(f'P{i}', cats=[pub, internal]); p.created_at = base + timedelta(minutes=i)
    secret = make_product('OnlyInternal', cats=[internal]); draft = make_product('Draft', cats=[pub, internal], status='draft')
    db.session.commit()
    s = HomepageSection(title='', source_category_id=internal.id, product_limit=10)
    db.session.add(s); db.session.commit()
    assert s.display_title == 'Picks'                      # category name is the title when none is set
    names = [p.name for p in svc.section_products(s)]
    assert len(names) == 10 and names[0] == 'P11' and 'OnlyInternal' not in names and 'Draft' not in names
    p12 = make_product('P12', cats=[pub, internal]); p12.created_at = base + timedelta(hours=1); db.session.commit()
    assert svc.section_products(s)[0].name == 'P12'        # updates automatically
    html = app.test_client().get('/').get_data(as_text=True)
    assert 'hscroll' in html and 'Picks' in html and 'OnlyInternal' not in html


def test_banners_resolve_links(app, client):
    cat = make_cat('Shirts'); internal = make_cat('Hidden', is_internal=True); p = make_product('Hat', cats=[cat])
    db.session.add_all([Banner(title='A', image_url='/x.jpg', link_type='product', product_id=p.id, position=1),
                        Banner(title='B', image_url='/y.jpg', link_type='category', category_id=cat.id, position=2),
                        Banner(title='C', image_url='/z.jpg', link_type='category', category_id=internal.id, position=3),
                        Banner(title='D', image_url='/w.jpg', link_type='none', position=4, is_active=False)])
    db.session.commit()
    with app.test_request_context():
        items = svc.active_banners()
    assert [i['banner'].title for i in items] == ['A', 'B', 'C']
    assert items[0]['href'] == f'/product/{p.slug}' and items[1]['href'] == '/category/shirts' and items[2]['href'] is None
    html = client.get('/').get_data(as_text=True)
    assert 'carousel' in html and f'/product/{p.slug}' in html and '/category/hidden' not in html


def test_catalog_routes_chips_and_legacy_redirect(app, client):
    cat = make_cat('Shirts'); make_product('Tee', cats=[cat], tags='summer')
    assert client.get(f'/?category={cat.id}').headers['Location'].endswith('/category/shirts')
    assert client.get('/?q=tee').status_code == 302
    html = client.get('/category/shirts?tag=summer&min_price=5').get_data(as_text=True)
    assert 'chip' in html and 'Tee' in html and 'In stock only' in html
    assert client.get('/categories').status_code == 200


def test_category_filter_option_and_autoselect(app, client):
    men = make_cat('Men'); tees = make_cat('Tees', men); women = make_cat('Women'); internal = make_cat('Picks', is_internal=True)
    make_product('Tee', cats=[tees]); make_product('Dress', cats=[women]); make_product('Secret', cats=[internal])
    names = lambda **kw: {p.name for p in svc.search_products(CatalogFilters(per_page=50, **kw)).items}
    html = client.get('/shop').get_data(as_text=True)
    assert 'name="cat" value="men"' in html and 'name="cat" value="picks"' not in html      # tree offered, internal hidden
    cats = lambda slugs: CatalogFilters.from_args(__import__('werkzeug.datastructures', fromlist=['MultiDict']).MultiDict([('cat', s) for s in slugs])).cats
    assert names(cats=cats(['men'])) == {'Tee'}                                             # includes descendants
    assert names(cats=cats(['men', 'women'])) == {'Tee', 'Dress'}                           # several categories (OR)
    assert cats(['picks']) == []                                                            # internal cannot be selected publicly
    page = client.get('/category/tees').get_data(as_text=True)
    assert 'value="tees" id=' in page and 'checked' in page.split('value="tees" id=')[1][:60]   # auto-selected on category page
    shop = client.get('/shop?cat=women&cat=tees').get_data(as_text=True)
    assert shop.count('class="chip"') >= 2 and 'Dress' in shop and 'Tee' in shop


def test_staff_product_form_renders_with_existing_data(app):
    from .conftest import make_user
    from app.models import Tag
    cat = make_cat('Clothes'); p = make_product('Tee', cats=[cat], options='Color: Red, Blue', tags='a, b', attributes='Material: Cotton')
    staff = make_user('09120000002', 'staff'); c = app.test_client(); login(c, staff)
    for url in ['/staff/products/new', f'/staff/products/{p.id}/edit', f'/staff/categories/{cat.id}/edit']:
        assert c.get(url).status_code == 200, url
    html = c.get(f'/staff/products/{p.id}/edit').get_data(as_text=True)
    assert 'Material: Cotton' in html and 'name="tag_ids"' in html


def test_category_filter_option_and_preselection(app, client):
    men = make_cat('Men'); tops = make_cat('Tops', men); women = make_cat('Women'); internal = make_cat('Picks', is_internal=True)
    make_product('Tee', cats=[tops]); make_product('Dress', cats=[women]); make_product('Coat', cats=[men])
    names = lambda f: {p.name for p in svc.search_products(f).items}
    from werkzeug.datastructures import MultiDict
    f = CatalogFilters.from_args(MultiDict([('cat', 'men'), ('cat', 'women')]))
    assert [c.slug for c in f.cats] == ['men', 'women'] and names(f) == {'Tee', 'Dress', 'Coat'}      # OR + descendants
    assert names(CatalogFilters.from_args(MultiDict([('cat', 'tops')]))) == {'Tee'}
    assert CatalogFilters.from_args(MultiDict([('cat', 'picks')])).cats == []                           # internal never selectable
    shop = client.get('/shop').get_data(as_text=True)
    assert 'name="cat" value="men"' in shop and 'checked' not in shop.split('name="cat" value="men"')[1][:80]
    page = client.get('/category/tops').get_data(as_text=True)                                          # current category pre-selected
    assert 'value="tops" id="c-%d"' % tops.id in page and 'checked' in page.split('value="tops" id="c-%d"' % tops.id)[1][:80]
    assert '<details open>' in page or 'open' in page.split('Categories')[1][:400]                      # its ancestors are expanded
    chips = client.get('/shop?cat=women').get_data(as_text=True)
    assert 'chip' in chips and 'Dress' in chips and 'Tee' not in chips.split('grid--catalog')[1]


def test_language_setting_switches_direction_and_text(app, client):
    from app.models import StoreSettings
    cat = make_cat('Shirts'); make_product('Tee', cats=[cat], tags='a')
    en = client.get('/shop').get_data(as_text=True)
    assert 'dir="ltr"' in en and 'bootstrap.min.css' in en and 'Add to cart' not in en and 'Filters' in en
    s = StoreSettings.query.first(); s.locale = 'fa'; db.session.commit()
    fa = client.get('/shop').get_data(as_text=True)
    assert 'lang="fa"' in fa and 'dir="rtl"' in fa and 'bootstrap.rtl.min.css' in fa and 'فیلترها' in fa and 'Filters' not in fa
    assert 'جستجو' in client.get('/auth/login').get_data(as_text=True) or 'ورود' in client.get('/auth/login').get_data(as_text=True)
    assert 'dir="rtl"' in client.get('/auth/login').get_data(as_text=True)
    for url in ['/', '/categories', '/shop?cat=shirts', '/product/tee']:
        assert client.get(url).status_code == 200
    cust = make_user('09120000050'); login(client, cust)
    assert 'سبد خرید' in client.get('/cart').get_data(as_text=True)
    staff = make_user('09120000051', 'staff'); c = app.test_client(); login(c, staff)
    r = c.post('/staff/settings', data={'store_name': 'Test', 'currency': 'IRT', 'locale': 'en'}); assert r.status_code == 302
    assert 'dir="ltr"' in client.get('/shop').get_data(as_text=True)
    assert c.post('/staff/settings', data={'store_name': 'Test', 'currency': 'IRT', 'locale': 'xx'}).status_code == 200


def test_staff_panel_renders_in_rtl(app):
    from app.models import StoreSettings
    StoreSettings.query.first().locale = 'fa'; db.session.commit()
    staff = make_user('09120000052', 'staff'); c = app.test_client(); login(c, staff)
    cat = make_cat('Men'); make_product('Tee', cats=[cat], tags='a')
    for url in ['/staff/', '/staff/products', '/staff/products/new', '/staff/categories', '/staff/tags', '/staff/import',
                '/staff/orders', '/staff/settings', '/staff/homepage', '/staff/banners', '/staff/coupons', '/staff/shipping']:
        r = c.get(url); assert r.status_code == 200 and 'dir="rtl"' in r.get_data(as_text=True), url
    assert 'تنظیمات فروشگاه' in c.get('/staff/settings').get_data(as_text=True)
