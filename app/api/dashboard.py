import os

import jwt
from dash import Dash, dcc, html, page_container, page_registry
from dash.dependencies import Input, Output
from flask import Flask, redirect, request, session
from requests_oauthlib import OAuth2Session

from flask_session import Session

# Config & ENV
DEBUG_MODE = os.getenv("DASH_DEBUG", "False").lower() == "true"
DASH_ENV = os.getenv("DASH_ENV", "development")

COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
COGNITO_DOMAIN = os.getenv(
    "COGNITO_DOMAIN"
)  # e.g. myapp.auth.eu-west-3.amazoncognito.com
COGNITO_REDIRECT_URI = os.getenv(
    "COGNITO_REDIRECT_URI"
)  # e.g. http://localhost:7777/callback
COGNITO_LOGOUT_URI = os.getenv("COGNITO_LOGOUT_URI", "http://localhost:7777")
COGNITO_SCOPE = ["openid", "email", "profile"]
SECRET_KEY = os.getenv("SECRET_KEY", "dev_key")

# OAuth URLs
AUTHORIZATION_BASE_URL = f"https://{COGNITO_DOMAIN}/oauth2/authorize"
TOKEN_URL = f"https://{COGNITO_DOMAIN}/oauth2/token"
USERINFO_URL = f"https://{COGNITO_DOMAIN}/oauth2/userInfo"
LOGOUT_URL = f"https://{COGNITO_DOMAIN}/logout"

# Flask setup
server = Flask(__name__)
server.secret_key = SECRET_KEY
server.config["SESSION_TYPE"] = "filesystem"
Session(server)


@server.route("/health")
def health_check():
    return "OK", 200


# Cognito OAuth
def get_cognito():
    return OAuth2Session(
        client_id=COGNITO_CLIENT_ID,
        redirect_uri=COGNITO_REDIRECT_URI,
        scope=COGNITO_SCOPE,
    )


@server.route("/login")
def login():
    cognito = get_cognito()
    authorization_url, _ = cognito.authorization_url(AUTHORIZATION_BASE_URL)
    return redirect(authorization_url)


@server.route("/callback")
def callback():
    cognito = get_cognito()
    token = cognito.fetch_token(
        TOKEN_URL,
        authorization_response=request.url,
        client_secret=COGNITO_CLIENT_SECRET,
    )
    session["oauth_token"] = token

    id_token = token.get("id_token")
    if id_token:
        decoded = jwt.decode(id_token, options={"verify_signature": False})
        session["user"] = decoded
    else:
        session["user"] = cognito.get(USERINFO_URL).json()

    return redirect("/")


@server.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# Check if user is authenticated (i.e., session contains valid data)
def is_logged_in():
    return "oauth_token" in session and "user" in session


# Check if authenticated user is approved (based on custom attribute)
def is_approved():
    if is_logged_in():
        user = session["user"]
        return user.get("custom:approved", "false").lower() == "true"
    return False


# Optional: Combine both if needed
def is_logged_in_and_approved():
    return is_logged_in() and is_approved()


@server.before_request
def require_login():
    exact_allowed_paths = {
        "/",  # home page (public)
        "/login",
        "/callback",
        "/logout",
        "/health",
    }
    prefix_allowed_paths = (
        "/_dash",  # Dash assets
        "/assets",  # static assets
    )

    if request.path in exact_allowed_paths or any(
        request.path.startswith(p) for p in prefix_allowed_paths
    ):
        return  # allow access to these paths without login

    if not is_logged_in_and_approved():
        return redirect("/login")


# Dash app setup
external_css = [
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css",
]

app = Dash(
    __name__,
    pages_folder="../services/pages",
    use_pages=True,
    external_stylesheets=external_css,
    external_scripts=[
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
    ],
    server=server,
    url_base_pathname="/",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)


@server.route("/")
def dash_home():
    return app.index()


def generate_pages_links():
    return [
        dcc.Link(
            page["name"],
            href=page["relative_path"],
            className="nav-link",
            style={
                "padding": "0 10px",
                "fontSize": "1.1rem",  # or "18px"
                "fontWeight": "500",  # optional: makes text slightly bolder
            },
        )
        for page in page_registry.values()
    ]


def navbar():
    img_tag = html.Img(
        src="assets/PG.png", width=27, className="d-inline-block align-text-middle me-2"
    )
    brand_link = dcc.Link(
        [img_tag, "Dash Lab"],
        href="/",
        className="navbar-brand d-flex align-items-center",
    )
    logout_link = html.A(
        "Logout",
        href="/logout",
        className="nav-link",
        style={
            "padding": "0 10px",
            "fontSize": "1.1rem",
            "color": "white",
            "cursor": "pointer",
        },
    )
    pages_links = generate_pages_links()

    # Wrap links inside <ul class="navbar-nav ms-auto"> and each link inside <li class="nav-item">
    nav_items = [html.Li(link, className="nav-item") for link in pages_links] + [
        html.Li(logout_link, className="nav-item")
    ]

    return html.Nav(
        className="navbar navbar-expand-lg bg-dark fixed-top",
        **{"data-bs-theme": "dark"},
        children=[
            html.Div(
                className="container-fluid d-flex align-items-center",
                children=[
                    brand_link,
                    html.Button(
                        className="navbar-toggler",
                        type="button",
                        **{
                            "data-bs-toggle": "collapse",
                            "data-bs-target": "#navbarSupportedContent",
                            "aria-controls": "navbarSupportedContent",
                            "aria-expanded": "false",
                            "aria-label": "Toggle navigation",
                        },
                        children=html.Span(className="navbar-toggler-icon"),
                    ),
                    html.Div(
                        className="collapse navbar-collapse justify-content-left",  # centers nav links
                        id="navbarSupportedContent",
                        children=[
                            html.Ul(
                                nav_items,
                                className="navbar-nav mb-2 mb-lg-0",  # mx-auto centers the list
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),  # track URL for callback
        html.Div(id="navbar-container", className="fixed-top"),
        html.Div(
            [
                html.Br(),
                page_container,
            ],
            className="container",
            style={"paddingTop": "70px", "minHeight": "100vh"},
        ),
    ],
    style={"background-color": "#e3f2fd"},
)


@app.callback(Output("navbar-container", "children"), Input("url", "pathname"))
def update_navbar(pathname):
    # Only show navbar if logged in
    if is_logged_in_and_approved():
        return navbar()
    return None


# Run locally only in development mode
if __name__ == "__main__" and DASH_ENV == "development":
    app.run(host="0.0.0.0", port=7777, debug=DEBUG_MODE)
