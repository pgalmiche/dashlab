import jwt
from dash import Dash, dcc, html, page_container, page_registry
from dash.dependencies import Input, Output
from flask import Flask, redirect, request, session
from requests_oauthlib import OAuth2Session

from config.settings import settings
from flask_session import Session

# Constants
DEBUG_MODE = settings.debug
DASH_ENV = settings.env
COGNITO_SCOPE = ["openid", "email", "profile"]

# OAuth URLs
AUTHORIZATION_BASE_URL = f"https://{settings.cognito_domain}/oauth2/authorize"
TOKEN_URL = f"https://{settings.cognito_domain}/oauth2/token"
USERINFO_URL = f"https://{settings.cognito_domain}/oauth2/userInfo"
LOGOUT_URL = f"https://{settings.cognito_domain}/logout"

# Flask setup
server = Flask(__name__)
server.secret_key = settings.secret_key
server.config["SESSION_TYPE"] = "filesystem"
Session(server)


@server.route("/health")
def health_check():
    return "OK", 200


# Cognito OAuth
def get_cognito():
    return OAuth2Session(
        client_id=settings.cognito_client_id,
        redirect_uri=settings.cognito_redirect_uri,
        scope=COGNITO_SCOPE,
    )


@server.route("/login")
def login():
    cognito = get_cognito()
    authorization_url, state = cognito.authorization_url(AUTHORIZATION_BASE_URL)
    session["oauth_state"] = state  # store the state
    return redirect(authorization_url)


@server.route("/callback")
def callback():
    cognito = get_cognito()
    token = cognito.fetch_token(
        TOKEN_URL,
        authorization_response=request.url,
        client_secret=settings.cognito_client_secret,
        state=session.get("oauth_state"),  # validate the state here
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


def is_logged_in():
    return "oauth_token" in session and "user" in session


def is_approved():
    if is_logged_in():
        user = session["user"]
        return user.get("custom:approved", "false").lower() == "true"
    return False


def is_logged_in_and_approved():
    return is_logged_in() and is_approved()


@server.before_request
def require_login():
    exact_allowed_paths = {
        "/",
        "/login",
        "/callback",
        "/logout",
        "/health",
    }
    prefix_allowed_paths = ("/_dash", "/assets")

    if request.path in exact_allowed_paths or any(
        request.path.startswith(p) for p in prefix_allowed_paths
    ):
        return

    if not is_logged_in_and_approved():
        return redirect("/login")


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
                "fontSize": "1.1rem",
                "fontWeight": "500",
            },
        )
        for page in page_registry.values()
    ]


def navbar():
    img_tag = html.Img(
        src="assets/PG.png",
        width=27,
        className="d-inline-block align-text-middle me-2",
    )
    brand_link = dcc.Link(
        [img_tag, "DashLab"],
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
    nav_items = [html.Li(link, className="nav-item") for link in generate_pages_links()]
    nav_items.append(html.Li(logout_link, className="nav-item"))

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
                        className="collapse navbar-collapse justify-content-left",
                        id="navbarSupportedContent",
                        children=[
                            html.Ul(nav_items, className="navbar-nav mb-2 mb-lg-0"),
                        ],
                    ),
                ],
            ),
        ],
    )


app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
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
    if is_logged_in_and_approved():
        return navbar()
    return None
