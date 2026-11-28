"""Product photos: the admin uploads one (and sees it), customers see it with every detail
in the shop's details window."""
import os
from io import BytesIO

from app import app as flask_app, db, Product
from tests.conftest import login_as, PROOF_PNG

FORM = {'name': 'T-Force Delta RGB RAM', 'category': 'memory', 'price': '2450.00', 'sale_price': '',
        'stock_quantity': '5', 'compatibility': 'DDR5', 'description': '16 GB kit\n6000 MT/s', 'image_url': ''}


def _photo(name='ram.png', data=PROOF_PNG, mime='image/png'):
    return (BytesIO(data), name, mime)


def _stored(url):
    return os.path.join(flask_app.config['PRODUCT_IMAGE_FOLDER'], url.rsplit('/', 1)[-1])


def test_the_admin_adds_a_product_with_a_photo_and_sees_it(client, admin):
    login_as(client, admin)
    client.post('/admin/products', data={**FORM, 'image_file': _photo()}, content_type='multipart/form-data')
    p = Product.query.one()
    assert p.image_url.startswith('/product-images/prod_') and os.path.exists(_stored(p.image_url))
    r = client.get(p.image_url)
    assert r.status_code == 200 and r.data == PROOF_PNG and r.headers['X-Content-Type-Options'] == 'nosniff'
    page = client.get('/admin/products').get_data(as_text=True)
    assert f'src="{p.image_url}"' in page and 'Photo of T-Force Delta RGB RAM' in page
    assert 'enctype="multipart/form-data"' in page and 'name="image_file"' in page


def test_replacing_or_removing_the_photo_deletes_the_old_file_and_editing_keeps_it(client, admin):
    login_as(client, admin)
    client.post('/admin/products', data={**FORM, 'image_file': _photo()}, content_type='multipart/form-data')
    p = Product.query.one()
    first = p.image_url
    client.post(f'/admin/products/{p.id}', data={**FORM, 'price': '2300.00'}, content_type='multipart/form-data')
    assert db.session.get(Product, p.id).image_url == first                       # an edit keeps the photo
    client.post(f'/admin/products/{p.id}', data={**FORM, 'image_file': _photo('new.png')},
                content_type='multipart/form-data')
    second = db.session.get(Product, p.id).image_url
    assert second != first and not os.path.exists(_stored(first)) and os.path.exists(_stored(second))
    client.post(f'/admin/products/{p.id}', data={**FORM, 'remove_image': '1'}, content_type='multipart/form-data')
    assert db.session.get(Product, p.id).image_url is None and not os.path.exists(_stored(second))


def test_only_real_images_are_accepted(client, admin):
    login_as(client, admin)
    page = client.post('/admin/products', data={**FORM, 'image_file': _photo('virus.exe', b'MZ' + b'\0' * 64,
                                                                             'application/octet-stream')},
                       content_type='multipart/form-data', follow_redirects=True).get_data(as_text=True)
    assert 'JPG, PNG or WEBP' in page and Product.query.count() == 0
    client.post('/admin/products', data={**FORM, 'image_file': _photo('fake.png', b'not an image at all', 'image/png')},
                content_type='multipart/form-data')
    assert Product.query.count() == 0                                              # the bytes must be a real PNG
    assert client.get('/product-images/../app.py').status_code == 404
    assert client.get('/product-images/prod_0000000000000000.png').status_code == 404


def test_the_details_window_has_the_photo_and_every_detail(client, customer):
    p = Product(name='T-Force Delta RGB RAM', price=2450, stock_quantity=5, is_active=True, category='memory',
                compatibility='DDR5', description='16 GB kit', image_url='/product-images/prod_0123456789abcdef.png')
    db.session.add(p)
    db.session.commit()
    login_as(client, customer)
    page = client.get('/user/shop').get_data(as_text=True)
    assert '"image": "/product-images/prod_0123456789abcdef.png"' in page
    for part in ('id="modalImg"', 'id="modalCategory"', 'id="modalCompat"', 'id="modalStock"', 'id="modalDesc"'):
        assert part in page, part
    assert 'Sale −' not in page.split('id="productGrid"')[-1].split('id="productModal"')[0]   # not on sale: no badge
    css = open(os.path.join('static', 'css', 'user.css'), encoding='utf-8').read()
    assert '.shop-badge[hidden]' in css                                            # the hidden sale badge stays hidden
