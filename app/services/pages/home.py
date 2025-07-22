import dash
from dash import Input, Output, dcc, html
from flask import session

dash.register_page(__name__, path="/", name="Home", order=0)

layout = html.Div(
    children=[
        dcc.Location(id="url", refresh=False),  # Needed to trigger callback
        html.Div(
            className="container py-5",
            children=[
                html.H1("Welcome to DashLab 👋", className="fw-bold mb-3"),
                html.P(
                    "DashLab is a personal space for experimenting with data science tools, models, "
                    "and visualizations using Plotly Dash.",
                    className="lead",
                ),
                html.P(
                    [
                        "Explore interactive datasets, statistical summaries, and machine learning demos — all from one place.",
                        html.Br(),
                        html.Br(),
                        "👤 Head over to my ",
                        html.A(
                            "personal portfolio",
                            href="https://pierregalmiche.link/about",
                            target="_blank",
                            className="text-primary",
                        ),
                        " to discover more about who I am and what I’m working on.",
                    ],
                    className="mb-4",
                ),
                html.Div(
                    className="alert alert-info",
                    children=[
                        "⚠️ Due to resource costs, users must be logged in to access projects.",
                        html.Br(),
                        "You can log in by clicking on any project link below or by clicking the Login button.",
                    ],
                ),
                html.Div(
                    html.P(
                        "🔒 Authentication is required to access protected data pages."
                    ),
                    className="text-muted",
                ),
                html.H2("Available Sections", className="h4 mt-4 mb-3"),
                html.Ul(
                    [
                        html.Li(
                            html.A(
                                "📁 File Explorer",
                                href="/file-explorer",
                                className="link-primary",
                            )
                        ),
                    ],
                    className="mb-4",
                ),
                html.Div(
                    id="auth-banner", className="mb-4"
                ),  # Dynamic auth banner here
            ],
        ),
    ],
)


@dash.callback(Output("auth-banner", "children"), Input("url", "pathname"))
def update_auth_banner(_):
    try:
        if "user" in session:

            user = session["user"]
            approved = user.get("custom:approved", "false").lower()
            if approved != "true":
                # Pending approval banner + logout button
                return html.Div(
                    [
                        html.Div(
                            className="alert alert-warning",
                            children=[
                                "⏳ You are logged in, but your account is pending admin approval.",
                                html.Br(),
                                "Please wait until an admin activates your account.",
                            ],
                        ),
                        html.A(
                            "Logout",
                            href="/logout",
                            className="btn btn-danger",
                            role="button",
                        ),
                    ]
                )
            else:
                # Approved user - show logout button + welcome message
                return html.Div(
                    [
                        html.Div(
                            className="alert alert-success",
                            children=[
                                "✅ You are logged in.",
                                html.Br(),
                                "Have fun exploring the available projects!",
                            ],
                        ),
                        html.A(
                            "Logout",
                            href="/logout",
                            className="btn btn-danger",
                            role="button",
                        ),
                    ]
                )
    except RuntimeError:
        # Happens when session not accessible
        pass

    # Not logged in: show login/signup buttons
    return html.Div(
        [
            html.A(
                "Login",
                href="/login",
                className="btn btn-primary me-2",
                role="button",
            ),
        ]
    )
