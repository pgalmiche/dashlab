"""
DashLab Dashboard with AWS Cognito Authentication

This module sets up a Flask server integrated with a Dash application,
using AWS Cognito OAuth2 for user authentication and authorization.

Features:
- OAuth2 login/logout flow via Cognito
- User session management stored on the filesystem inside the Docker container
- Access control ensuring only logged-in and approved users can access protected routes
- Dynamic navigation bar based on user authentication state
- Healthcheck endpoint for monitoring

Dependencies:
- Flask for server and session management
- Dash for building the interactive web application UI
- requests-oauthlib for handling OAuth2 sessions
- PyJWT for decoding JWT tokens from Cognito

Configuration:
- All sensitive keys and URLs are loaded from the `config.settings` module
- Session files are stored in `/tmp/flask_session` within the container

Usage:
Run the Flask server which serves both the OAuth routes and the Dash app.
"""

import jwt
from dash import Dash, dcc, html, page_container, page_registry
from dash.dependencies import Input, Output
from flask import Flask, redirect, request, session
from flask_session import Session
from requests_oauthlib import OAuth2Session

# from app.services.pages.file_explorer import register_file_explorer_page
from config.settings import settings

# --- Configuration constants ---
DEBUG_MODE = settings.debug
DASH_ENV = settings.env
COGNITO_SCOPE = ['openid', 'email', 'profile']

# --- Cognito OAuth endpoints ---
AUTHORIZATION_BASE_URL = f'https://{settings.cognito_domain}/oauth2/authorize'
TOKEN_URL = f'https://{settings.cognito_domain}/oauth2/token'
USERINFO_URL = f'https://{settings.cognito_domain}/oauth2/userInfo'
LOGOUT_URL = f'https://{settings.cognito_domain}/logout'

# --- Flask server setup ---
server = Flask(__name__)
server.secret_key = settings.secret_key
server.config['SESSION_TYPE'] = 'filesystem'
# save flask_session in container and not local dev
server.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
Session(server)  # Enables session storage on the filesystem


# --- Healthcheck route ---
@server.route('/health')
def health_check():
    """Simple healthcheck endpoint."""
    return 'OK', 200


# --- OAuth2 client setup using Cognito ---
def get_cognito():
    """Initialize a new Cognito OAuth2 session."""
    return OAuth2Session(
        client_id=settings.cognito_client_id,
        redirect_uri=settings.cognito_redirect_uri,
        scope=COGNITO_SCOPE,
    )


# --- Login route ---
@server.route('/login')
def login():
    """Start OAuth login flow with Cognito."""
    cognito = get_cognito()
    authorization_url, state = cognito.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth_state'] = state  # Save state to validate on callback
    return redirect(authorization_url)


# --- OAuth callback route ---
@server.route('/callback')
def callback():
    """Handle redirect from Cognito after login."""
    cognito = get_cognito()
    token = cognito.fetch_token(
        TOKEN_URL,
        authorization_response=request.url,
        client_secret=settings.cognito_client_secret,
        state=session.get('oauth_state'),  # Ensure state matches
    )
    session['oauth_token'] = token

    # Extract user info from ID token or userinfo endpoint
    id_token = token.get('id_token')
    if id_token:
        decoded = jwt.decode(id_token, options={'verify_signature': False})
        session['user'] = decoded
    else:
        session['user'] = cognito.get(USERINFO_URL).json()

    return redirect('/')


# --- Logout route ---
@server.route('/logout')
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect('/')


# --- Session/user access helpers ---
def is_logged_in():
    """Check if user is logged in via OAuth."""
    return 'oauth_token' in session and 'user' in session


def is_approved():
    """Check if logged-in user is approved (via Cognito custom attribute)."""
    if is_logged_in():
        user = session['user']
        return user.get('custom:approved', 'false').lower() == 'true'
    return False


def is_logged_in_and_approved():
    """Return True if user is logged in and approved."""
    return is_logged_in() and is_approved()


# --- Protect all routes except public/static ones ---
@server.before_request
def require_login():
    """Redirect to login if user is not authenticated and approved."""
    exact_allowed_paths = {'/', '/login', '/callback', '/logout', '/health'}
    prefix_allowed_paths = ('/_dash', '/assets')

    if request.path in exact_allowed_paths or any(
        request.path.startswith(p) for p in prefix_allowed_paths
    ):
        return

    if not is_logged_in_and_approved():
        return redirect('/login')


# --- Dash app setup ---
external_css = [
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css',
]

app = Dash(
    __name__,
    pages_folder='../services/pages',
    use_pages=True,
    external_stylesheets=external_css,
    external_scripts=[
        'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'
    ],
    server=server,
    url_base_pathname='/',
    meta_tags=[{'name': 'viewport', 'content': 'width=device-width, initial-scale=1'}],
)

# register_file_explorer_page()


# --- Route to render Dash app at root ---
@server.route('/')
def dash_home():
    """Render Dash index."""
    return app.index()


# --- Navigation UI helpers ---
def generate_pages_links():
    """Generate navigation links from Dash pages registry."""
    return [
        dcc.Link(
            page['name'],
            href=page['relative_path'],
            className='nav-link',
            style={
                'padding': '0 10px',
                'fontSize': '1.1rem',
                'fontWeight': '500',
            },
        )
        for page in page_registry.values()
    ]


def navbar():
    """Construct the navigation bar UI."""
    img_tag = html.Img(
        src='assets/PG.png',
        width=27,
        className='d-inline-block align-text-middle me-2',
    )

    brand_link = dcc.Link(
        [img_tag, 'DashLab'],
        href='/',
        className='navbar-brand d-flex align-items-center',
    )

    logout_link = html.A(
        'Logout',
        href='/logout',
        className='nav-link',
        style={
            'padding': '0 10px',
            'fontSize': '1.1rem',
            'color': 'white',
            'cursor': 'pointer',
        },
    )

    nav_items = [html.Li(link, className='nav-item') for link in generate_pages_links()]
    nav_items.append(html.Li(logout_link, className='nav-item'))

    return html.Nav(
        className='navbar navbar-expand-lg bg-dark fixed-top',
        **{'data-bs-theme': 'dark'},
        children=[
            html.Div(
                className='container-fluid d-flex align-items-center',
                children=[
                    brand_link,
                    html.Button(
                        className='navbar-toggler',
                        type='button',
                        **{
                            'data-bs-toggle': 'collapse',
                            'data-bs-target': '#navbarSupportedContent',
                            'aria-controls': 'navbarSupportedContent',
                            'aria-expanded': 'false',
                            'aria-label': 'Toggle navigation',
                        },
                        children=html.Span(className='navbar-toggler-icon'),
                    ),
                    html.Div(
                        className='collapse navbar-collapse justify-content-left',
                        id='navbarSupportedContent',
                        children=[
                            html.Ul(nav_items, className='navbar-nav mb-2 mb-lg-0'),
                        ],
                    ),
                ],
            ),
        ],
    )


# --- Main layout of the Dash app ---
app.layout = html.Div(
    [
        dcc.Location(id='url', refresh=False),
        html.Div(id='navbar-container', className='fixed-top'),
        html.Div(
            [
                html.Br(),
                page_container,  # Placeholder for pages
            ],
            className='container',
            style={'paddingTop': '70px', 'minHeight': '100vh'},
        ),
    ],
    style={'background-color': '#e3f2fd'},
)


# --- Callback to update navbar dynamically ---
@app.callback(Output('navbar-container', 'children'), Input('url', 'pathname'))
def update_navbar(pathname):
    """Show navbar only if user is logged in and approved."""
    if is_logged_in_and_approved():
        return navbar()
    # TODO limit access according to pathname
    return None
