"""Customer registration: the full name is optional, and the mobile number must be a real
Philippine mobile number, typed as 09171234567 or +639171234567 and saved as +639171234567."""
import pytest

from app import db, Customer, name_from_email
from services.ph_phone import check_ph_mobile


def _register(client, **fields):
    data = {'fullName': 'Cara Santos', 'email': 'cara@example.com', 'password': 'Secret#123',
            'rePassword': 'Secret#123', 'phone': '09171234567'}
    data.update(fields)
    return client.post('/register', data=data, follow_redirects=True)


# ---- the rule (services/ph_phone.py) ----

@pytest.mark.parametrize('typed', ['09171234567', '+639171234567', '0917 123 4567', '+63 917-123-4567',
                                   '09951234567', '09661234567'])
def test_valid_philippine_mobile_numbers_are_saved_as_plus_63(typed):
    assert check_ph_mobile(typed) == ('+63' + typed.replace(' ', '').replace('-', '')[-10:], None)


@pytest.mark.parametrize('typed, says', [
    ('0917123', 'Too short'),                         # 3. only 7 digits
    ('0917123456789', 'Too long'),                    # 4. 13 digits in local format
    ('12345678901', 'Incorrect prefix'),              # 5. invalid prefix
    ('09001234567', 'not a Philippine mobile network prefix'),   # 5. 09 but no network uses 0900
    ('+638171234567', 'must start with +639'),        # international, but not +639
    ('+63917123456', 'Too short'),
    ('0917ABC4567', 'not letters'),                   # 6. letters
    ('0917#123456', 'Use numbers only'),              # 7. unsupported symbols
    ('(0917) 123 4567', 'Use numbers only'),
    ('', 'Enter your mobile number'),                 # 9. empty
    (None, 'Enter your mobile number'),
])
def test_invalid_numbers_are_refused_with_a_clear_reason(typed, says):
    saved, problem = check_ph_mobile(typed)
    assert saved is None and says in problem


# ---- registration ----

@pytest.mark.parametrize('typed', ['09171234567', '+639171234567'])
def test_registration_with_either_format_saves_one_format(client, typed):       # 1, 2 and 10
    r = client.post('/register', data={'fullName': 'Cara Santos', 'email': 'cara@example.com', 'password': 'Secret#123',
                                       'rePassword': 'Secret#123', 'phone': typed})
    assert r.status_code == 302 and r.headers['Location'].endswith('/login')
    c = Customer.query.filter_by(email='cara@example.com').one()
    assert (c.full_name, c.phone) == ('Cara Santos', '+639171234567')


@pytest.mark.parametrize('typed', ['0917123', '0917123456789', '12345678901', '0917ABC4567', '0917#123456', ''])
def test_an_invalid_number_is_never_saved(client, typed):
    _register(client, phone=typed)
    assert Customer.query.count() == 0


@pytest.mark.parametrize('saved_before', ['+639171234567', '09171234567', '639171234567'])
def test_a_number_already_registered_is_refused_in_any_saved_format(client, saved_before):     # 8
    db.session.add(Customer(username='first', email='first@example.com', full_name='First', phone=saved_before,
                            password_hash='x'))
    db.session.commit()
    page = _register(client, phone='+63 917 123 4567').get_data(as_text=True)
    assert 'already registered to another account' in page
    assert Customer.query.count() == 1


def test_a_database_error_is_not_shown_to_the_customer(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def broken():
        raise OperationalError('INSERT INTO customers ...', {}, Exception('secret server detail'))
    monkeypatch.setattr(db.session, 'commit', broken)
    page = _register(client).get_data(as_text=True)
    assert 'could not be created right now' in page and 'secret server detail' not in page and 'INSERT' not in page


def test_the_full_name_is_optional(client):
    _register(client, fullName='   ', email='juan.dela-cruz@gmail.com')
    c = Customer.query.filter_by(email='juan.dela-cruz@gmail.com').one()
    assert c.full_name == 'Juan Dela Cruz'                 # changeable later in Profile
    assert name_from_email('x@y.z') == 'X'


def test_a_wrong_number_is_refused_and_the_form_keeps_what_was_typed(client):
    page = _register(client, phone='0917 123').get_data(as_text=True)
    assert Customer.query.count() == 0
    assert 'Too short' in page
    assert 'value="cara@example.com"' in page and 'value="0917 123"' in page
    assert 'Secret#123' not in page                                   # passwords are never sent back


def test_an_email_already_used_shows_nothing_about_the_account_or_what_was_typed(client, customer):
    customer.full_name = 'Maria Existing Owner'
    db.session.commit()
    r = client.post('/register', data={'fullName': 'Someone Else', 'email': customer.email, 'password': 'Secret#123',
                                       'rePassword': 'Secret#123', 'phone': '+63 912 345 6789'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/register')   # Back never re-sends it
    page = client.get('/register').get_data(as_text=True)
    assert 'already registered' in page
    for leak in ('Maria Existing Owner', customer.email, 'Someone Else', 'value="+63 912 345 6789"'):
        assert leak not in page, leak
    assert Customer.query.count() == 1


def test_the_create_account_button_locks_until_the_answer(client):
    page = client.get('/register').get_data(as_text=True)
    assert 'data-busy-text="Creating your account…"' in page and 'js/busy-guard.js' in page


def test_the_form_shows_the_rules(client):
    page = client.get('/register').get_data(as_text=True)
    assert '(optional)' in page and '09171234567 or +639171234567' in page
    assert 'data-ph-phone' in page and 'js/ph-phone.js' in page and 'aria-live="polite"' in page
    assert 'id="fullName"' in page and 'name="fullName" placeholder="Full name" maxlength="100"' in page
    assert 'required' not in page.split('id="fullName"')[1].split('>')[0]


# ---- strong passwords (customer and technician registration) ----

@pytest.mark.parametrize('password, missing', [
    ('secret#123', 'a capital letter'),
    ('SECRET#123', 'a small letter'),
    ('Secret#abc', 'a number'),
    ('Secret1234', 'a special character'),
    ('Se#1', 'at least 8 characters'),
])
def test_weak_passwords_say_what_they_still_need(password, missing):
    from services.password_rules import password_problem
    assert missing in password_problem(password)
    assert password_problem('Secret#123') is None


def test_a_weak_password_is_refused_at_registration(client):
    page = _register(client, password='secret123', rePassword='secret123').get_data(as_text=True)
    assert Customer.query.count() == 0
    assert 'a capital letter' in page and 'a special character' in page


def test_both_forms_show_the_checklist_and_required_marks(client):
    customer = client.get('/register').get_data(as_text=True)
    assert 'data-password-rules="password"' in customer and 'js/password-rules.js' in customer
    assert 'Fields marked <span class="req">*</span> are required' in customer
    assert 'Email <span class="req">*</span>' in customer and 'Mobile number <span class="req">*</span>' in customer
    assert 'Full name <span class="optional">(optional)</span>' in customer      # optional: no *
    tech = client.get('/technician/register').get_data(as_text=True)
    assert 'data-password-rules="password"' in tech and 'js/password-rules.js' in tech
    assert 'Full name (as printed on your ID) <span class="req">*</span>' in tech  # required for technicians
