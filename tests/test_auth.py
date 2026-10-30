from models import User


def test_user_registration_success(client, app):
    """Test standard customer registration."""
    response = client.post('/auth/register', data={
        'username': 'newuser',
        'email': 'newuser@example.com',
        'password': 'password123',
        'confirm_password': 'password123',
        'full_name': 'New User'
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='newuser').first()
        assert user is not None
        assert user.email == 'newuser@example.com'
        assert user.role == 'user'  # Normal registration must always be 'user'
        assert user.check_password('password123') is True


def test_registration_validation_errors(client):
    """Test validation errors for short password and mismatched passwords."""
    # Short password
    res1 = client.post('/auth/register', data={
        'username': 'shortpass',
        'email': 'short@example.com',
        'password': '123',
        'confirm_password': '123'
    }, follow_redirects=True)
    assert b'Password must be at least 6 characters long' in res1.data

    # Password mismatch
    res2 = client.post('/auth/register', data={
        'username': 'mismatch',
        'email': 'mismatch@example.com',
        'password': 'password123',
        'confirm_password': 'password999'
    }, follow_redirects=True)
    assert b'Passwords do not match' in res2.data


def test_registration_duplicate_username_and_email(client, normal_user):
    """Test that duplicate usernames or emails are rejected."""
    # Duplicate username
    res1 = client.post('/auth/register', data={
        'username': normal_user.username,
        'email': 'different@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    }, follow_redirects=True)
    assert b'Username is already taken' in res1.data

    # Duplicate email
    res2 = client.post('/auth/register', data={
        'username': 'unique_user',
        'email': normal_user.email,
        'password': 'password123',
        'confirm_password': 'password123'
    }, follow_redirects=True)
    assert b'An account with this email already exists' in res2.data


def test_login_success(client, normal_user):
    """Test user login with valid credentials."""
    response = client.post('/auth/login', data={
        'username_or_email': normal_user.email,
        'password': 'userpass123'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Welcome back' in response.data


def test_login_invalid_credentials(client, normal_user):
    """Test login failure on incorrect password."""
    response = client.post('/auth/login', data={
        'username_or_email': normal_user.username,
        'password': 'wrongpassword'
    }, follow_redirects=True)
    assert b'Invalid username/email or password' in response.data


def test_logout(client, normal_user):
    """Test logout flow."""
    client.post('/auth/login', data={
        'username_or_email': normal_user.username,
        'password': 'userpass123'
    }, follow_redirects=True)

    logout_res = client.get('/auth/logout', follow_redirects=True)
    assert logout_res.status_code == 200
    assert b'You have been signed out successfully' in logout_res.data
