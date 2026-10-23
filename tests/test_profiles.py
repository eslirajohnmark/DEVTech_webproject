"""Profile look (avatar, banner, display name) and editable profiles on all three portals."""
import io
import os

import pytest

from app import db, Customer, Technician, Admin
from tests.conftest import login_as

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00'
       b'\x00\x00\x00IEND\xaeB`\x82')


@pytest.fixture
def avatar_dir(app, tmp_path):
    app.config['AVATAR_UPLOAD_FOLDER'] = str(tmp_path / 'avatars')
    return tmp_path / 'avatars'


def _look(client, **fields):
    data = {'display_name': '', 'headline': '', 'avatar_mode': 'initials', 'avatar_color': 'ocean',
            'avatar_frame': 'ring', 'banner': 'aurora'}
    data.update(fields)
    return client.post('/account/appearance', data=data, content_type='multipart/form-data')


def test_defaults_differ_by_role(customer, technician, admin):
    assert (customer.avatar_color_key, technician.avatar_color_key, admin.avatar_color_key) == ('ocean', 'ember', 'mint')
    assert customer.avatar_mode == 'initials' and customer.initials == 'TC'
    assert customer.shown_name == 'Test Customer'


@pytest.mark.parametrize('who, back', [('customer', '/user/profile'), ('technician', '/technician/profile'),
                                       ('admin', '/admin/profile')])
def test_every_role_can_save_its_look(client, request, who, back):
    account = request.getfixturevalue(who)
    login_as(client, account)
    r = _look(client, display_name='Neo', headline='Fixes things', avatar_mode='icon',
              avatar_icon='robot', avatar_color='grape', avatar_frame='pulse', banner='nebula')
    assert r.status_code == 302 and r.headers['Location'].endswith(back + '#look')
    db.session.refresh(account)
    assert (account.shown_name, account.headline, account.avatar_icon, account.avatar_color,
            account.avatar_frame, account.banner) == ('Neo', 'Fixes things', 'robot', 'grape', 'pulse', 'nebula')
    assert account.avatar_mode == 'icon'
    page = client.get(back).get_data(as_text=True)
    assert 'fa-robot' in page and 'pf-banner--nebula' in page and 'Neo' in page


def test_unknown_choices_fall_back_safely(customer_logged_in, customer):
    _look(customer_logged_in, avatar_mode='icon', avatar_icon='<script>', avatar_color='hotpink',
          avatar_frame='x', banner='../../etc')
    db.session.refresh(customer)
    assert customer.avatar_icon is None and customer.avatar_mode == 'initials'
    assert (customer.avatar_color_key, customer.avatar_frame_key, customer.banner_key) == ('ocean', 'ring', 'aurora')


def test_too_long_display_name_rejected(customer_logged_in, customer):
    _look(customer_logged_in, display_name='x' * 61)
    db.session.refresh(customer)
    assert customer.display_name is None


def test_photo_upload_serve_and_replace(client, customer, technician, avatar_dir):
    login_as(client, customer)
    r = client.post('/account/appearance', data={'avatar_mode': 'photo',
                    'avatar_photo': (io.BytesIO(PNG), 'me.png', 'image/png')},
                    content_type='multipart/form-data')
    assert r.status_code == 302
    db.session.refresh(customer)
    first = customer.avatar_file
    assert first and first.endswith('.png') and (avatar_dir / first).is_file()
    assert client.get(f'/avatars/{first}').status_code == 200
    login_as(client, technician)                                 # other signed-in accounts can see it
    assert client.get(f'/avatars/{first}').status_code == 200
    client.get('/logout')
    assert client.get(f'/avatars/{first}').status_code == 302    # anonymous visitors cannot

    login_as(client, customer)
    _look(client, avatar_mode='icon', avatar_icon='cat')         # switching away deletes the file
    db.session.refresh(customer)
    assert customer.avatar_file is None and not (avatar_dir / first).exists()


def test_photo_upload_rejects_fakes_and_pdfs(customer_logged_in, customer, avatar_dir):
    for payload, name, mime in [(b'<script>alert(1)</script>', 'x.png', 'image/png'),
                                (b'%PDF-1.4 fake', 'x.pdf', 'application/pdf')]:
        customer_logged_in.post('/account/appearance', data={'avatar_mode': 'photo',
                                'avatar_photo': (io.BytesIO(payload), name, mime)},
                                content_type='multipart/form-data')
        db.session.refresh(customer)
        assert customer.avatar_file is None
    assert not avatar_dir.exists() or not os.listdir(avatar_dir)


def test_avatar_route_rejects_bad_names(customer_logged_in):
    assert customer_logged_in.get('/avatars/..%2F..%2Fapp.py').status_code == 404
    assert customer_logged_in.get('/avatars/notahexname.png').status_code == 404


def test_appearance_requires_login(client):
    assert _look(client).status_code == 302


def test_admin_profile_details_and_password(admin_logged_in, admin):
    r = admin_logged_in.post('/admin/profile', data={'action': 'details', 'full_name': 'Ada Lovelace',
                                                     'phone': '0917'})
    assert r.status_code == 302
    db.session.refresh(admin)
    assert admin.full_name == 'Ada Lovelace' and admin.phone == '0917'
    admin_logged_in.post('/admin/profile', data={'action': 'password', 'current_password': 'wrong',
                                                 'new_password': 'NewPass123', 'confirm_password': 'NewPass123'})
    assert db.session.get(Admin, admin.id).check_password('adminpass123')
    admin_logged_in.post('/admin/profile', data={'action': 'password', 'current_password': 'adminpass123',
                                                 'new_password': 'short', 'confirm_password': 'short'})
    assert db.session.get(Admin, admin.id).check_password('adminpass123')
    admin_logged_in.post('/admin/profile', data={'action': 'password', 'current_password': 'adminpass123',
                                                 'new_password': 'NewPass123', 'confirm_password': 'NewPass123'})
    assert db.session.get(Admin, admin.id).check_password('NewPass123')


def test_admin_profile_is_admin_only(customer_logged_in):
    assert customer_logged_in.get('/admin/profile').status_code == 302


def test_technician_can_edit_contact_details(tech_logged_in, technician):
    tech_logged_in.post('/technician/profile/details', data={
        'full_name': 'Tom Fixer', 'phone': '0918', 'address': '1 Rizal', 'city': 'Ormoc', 'province': 'Leyte',
        'email': 'hijack@x.test'})
    t = db.session.get(Technician, technician.id)
    assert (t.full_name, t.phone, t.city) == ('Tom Fixer', '0918', 'Ormoc')
    assert t.email == 'tech@test.local'                          # email is not editable here
    tech_logged_in.post('/technician/profile/details', data={'full_name': ''})
    assert db.session.get(Technician, technician.id).full_name == 'Tom Fixer'


def test_customer_password_rule_matches_site(customer_logged_in, customer):
    customer_logged_in.post('/user/profile', data={'full_name': 'Test Customer', 'current_password': 'customerpass1',
                                                   'new_password': 'abcdef', 'confirm_password': 'abcdef'})
    assert db.session.get(Customer, customer.id).check_password('customerpass1')


def test_layouts_show_avatar_and_password_toggle_script(client, customer, technician, admin):
    for account, url in [(customer, '/user/dashboard'), (technician, '/technician/dashboard'),
                         (admin, '/admin/dashboard')]:
        login_as(client, account)
        html = client.get(url).get_data(as_text=True)
        assert 'pf-avatar' in html and 'password-toggle.js' in html and 'css/profile.css' in html
    for url in ('/login', '/register', '/admin/login', '/technician/login', '/technician/register'):
        client.get('/logout')
        assert 'password-toggle.js' in client.get(url).get_data(as_text=True), url
