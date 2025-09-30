import os
from unittest.mock import MagicMock, patch

import pytest
from flask import session

from app.api import dashboard
from app.api.dashboard import server  # import Flask server

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


@pytest.fixture
def client():
    # Flask test client for the server
    dashboard.server.config['TESTING'] = True
    with dashboard.server.test_client() as client:
        yield client


def test_health_check(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.data == b'OK'


def test_login_redirect(client):
    response = client.get('/login', follow_redirects=False)
    # Should redirect to Cognito authorization URL
    assert response.status_code == 302
    assert 'https://' in response.headers['Location']


@patch('app.api.dashboard.get_cognito')
def test_callback_sets_session(mock_get_cognito, client):
    # Mock OAuth2Session behavior
    mock_cognito = mock_get_cognito.return_value
    mock_cognito.fetch_token.return_value = {
        'id_token': 'fake.token.value',
    }
    mock_cognito.get.return_value.json.return_value = {
        'email': 'test@example.com',
        'custom:approved': 'true',
    }

    with client.session_transaction() as sess:
        sess['oauth_state'] = 'mock_state'

    # Patch jwt.decode to return a decoded token dict
    with patch('app.api.dashboard.jwt.decode') as mock_jwt_decode:
        mock_jwt_decode.return_value = {
            'email': 'test@example.com',
            'custom:approved': 'true',
        }
        response = client.get(
            '/callback?state=mock_state&code=abc123', follow_redirects=False
        )
        assert response.status_code == 302  # Redirect to '/'

        # Session should now have oauth_token and user keys set
        with client.session_transaction() as sess:
            assert 'oauth_token' in sess
            assert 'user' in sess


def test_logout_clears_session(client):
    with client.session_transaction() as sess:
        sess['oauth_token'] = 'something'
        sess['user'] = {'email': 'test@example.com'}

    response = client.get('/logout', follow_redirects=False)
    assert response.status_code == 302
    assert response.headers['Location'] == '/'

    with client.session_transaction() as sess:
        assert 'oauth_token' not in sess
        assert 'user' not in sess


def test_require_login_redirects(client):
    # Access a protected route without login
    response = client.get('/some-protected-route', follow_redirects=False)
    # Should redirect to /login
    assert response.status_code == 302
    assert response.headers['Location'] == '/login'


def test_require_login_allows_public_routes(client):
    with (
        patch('app.api.dashboard.get_cognito') as mock_get_cognito,
        patch('jwt.decode') as mock_jwt_decode,
    ):

        mock_jwt_decode.return_value = {'sub': '1234567890'}  # dummy decoded payload

        mock_cognito = MagicMock()
        mock_cognito.fetch_token.return_value = {
            'access_token': 'dummy_token',
            'id_token': 'dummy_id_token',
        }
        mock_get_cognito.return_value = mock_cognito

        mock_cognito.authorization_url.return_value = (
            'https://example.com/auth',
            'dummy_state',
        )

        public_paths = ['/', '/login', '/callback', '/logout', '/health']
        for path in public_paths:
            url = path
            if path == '/callback':
                url += '?code=dummycode&state=dummystate'
            response = client.get(url)
            assert response.status_code in (200, 302)


def test_is_logged_in_and_approved_true():

    with server.test_request_context():
        # Set session manually in the context
        from flask import session

        session['oauth_token'] = 'fake-token'
        session['user'] = {'custom:approved': 'true'}

        assert dashboard.is_logged_in_and_approved() is True


def test_is_logged_in_and_approved_false():

    with server.test_request_context():
        from flask import session

        # no oauth_token or user in session means not logged in
        session.clear()
        assert dashboard.is_logged_in_and_approved() is False


def test_update_navbar_logged_in(mocker, client):
    # Patch session to simulate logged-in and approved user
    mocker.patch('app.api.dashboard.is_logged_in_and_approved', return_value=True)

    with client.application.test_request_context('/'):
        # simulate a logged-in user in session
        session['user'] = {'username': 'testuser'}

        result = dashboard.update_navbar('/')
        assert result is not None  # Should return navbar component


def test_update_navbar_not_logged_in(mocker, client):
    mocker.patch('app.api.dashboard.is_logged_in_and_approved', return_value=False)

    result = dashboard.update_navbar('/')
    assert result is None
