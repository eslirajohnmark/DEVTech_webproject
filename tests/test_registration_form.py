"""Customer registration: the full name is optional, and the mobile number must be a
12-digit Philippine mobile number (63, then 9 and nine more digits)."""
import pytest

from app import Customer, name_from_email, ph_mobile_number


def _register(client, **fields):
    data = {'fullName': 'Cara Santos', 'email': 'cara@example.com', 'password': 'Secret#123',
            'rePassword': 'Secret#123', 'phone': '+63 912 345 6789'}
    data.update(fields)
    return client.post('/register', data=data)


@pytest.mark.parametrize('typed, saved', [
    ('+63 912 345 6789', '+639123456789'),
    ('639123456789', '+639123456789'),
    ('+63-912-345-6789', '+639123456789'),
    ('(63) 912 345 6789', '+639123456789'),
])
def test_mobile_numbers_in_any_common_spacing_are_accepted(typed, saved):
    assert ph_mobile_number(typed) == saved


@pytest.mark.parametrize('typed', ['09123456789', '912 345 6789', '+63 912 345 678', '+63 912 345 67890',
                                   '+63 812 345 6789', '+1 912 345 6789', '63912345678a', '', None])
def test_other_numbers_are_refused(typed):
    assert ph_mobile_number(typed) is None


def test_registration_saves_the_number_in_one_format(client):
    r = _register(client)
    assert r.status_code == 302
    c = Customer.query.filter_by(email='cara@example.com').one()
    assert (c.full_name, c.phone) == ('Cara Santos', '+639123456789')


def test_the_full_name_is_optional(client):
    _register(client, fullName='   ', email='juan.dela-cruz@gmail.com')
    c = Customer.query.filter_by(email='juan.dela-cruz@gmail.com').one()
    assert c.full_name == 'Juan Dela Cruz'                 # changeable later in Profile
    assert name_from_email('x@y.z') == 'X'


def test_a_wrong_number_is_refused_and_the_form_keeps_what_was_typed(client):
    page = _register(client, phone='0912 345 6789').get_data(as_text=True)
    assert Customer.query.count() == 0
    assert '12-digit mobile number that starts with 63 9' in page
    assert 'value="cara@example.com"' in page and 'value="0912 345 6789"' in page


def test_the_form_shows_the_rules(client):
    page = client.get('/register').get_data(as_text=True)
    assert '(optional)' in page and '12 digits starting with 63 9' in page
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
