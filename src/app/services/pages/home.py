import dash
from dash import Input, Output, dcc, html
from flask import session

from app.services.utils.ui_utils import build_project_section
from config.settings import settings

image_tag = getattr(settings, 'image_tag', 'unknown')
if image_tag.startswith('v'):  # or some other way to detect a tag
    commit_link = f'https://gitlab.com/pgalmiche/dashlab/-/tags/{image_tag}'
else:
    commit_link = f'https://gitlab.com/pgalmiche/dashlab/-/commit/{image_tag}'


dash.register_page(__name__, path='/', name='Home', order=0)

layout = html.Div(
    children=[
        dcc.Location(id='url', refresh=False),  # Needed to trigger callback
        html.Div(
            className='container py-5',
            children=[
                html.H1('Welcome to DashLab 👋', className='fw-bold mb-3'),
                html.P(
                    'DashLab is a personal space for experimenting with data science tools, models, '
                    'and visualizations using Plotly Dash.',
                    className='lead',
                ),
                html.P(
                    [
                        'Explore interactive datasets, statistical summaries, and machine learning demos — all from one place.',
                        html.Br(),
                        html.P(
                            [
                                'Current image version: ',
                                html.Code(image_tag),
                                ' — corresponds to commit ',
                                html.A(
                                    image_tag,
                                    href=commit_link,
                                    target='_blank',
                                    className='text-primary',
                                ),
                                ' on GitLab project.',
                            ],
                            className='mt-3',
                        ),
                        html.Br(),
                        '👤 Visit my ',
                        html.A(
                            'personal portfolio',
                            href='https://pierregalmiche.link/about',
                            target='_blank',
                            className='text-primary',
                        ),
                        ' to learn more about who I am and what I’m working on.',
                        html.Br(),
                        html.Br(),
                        '📘 Full project documentation is available on the ',
                        html.A(
                            'GitLab Page',
                            href='https://pgalmiche.gitlab.io/dashlab/',
                            target='_blank',
                            className='text-primary',
                        ),
                        '.',
                        html.Br(),
                        '🧑‍💻 You can also explore the codebase and CI/CD pipelines on ',
                        html.A(
                            'GitLab',
                            href='https://gitlab.com/pgalmiche/dashlab',
                            target='_blank',
                            className='text-primary',
                        ),
                        '.',
                        html.Br(),
                        html.Br(),
                        "🛠️ To explore how I built this project and learn more about its dependencies, don't hesitate to visit my wiki: ",
                        html.A(
                            'MindShelf',
                            href='https://wiki.pierregalmiche.link',
                            target='_blank',
                            className='text-primary',
                        ),
                        '.',
                    ],
                    className='mb-4',
                ),
                html.Div(
                    className='alert alert-info',
                    children=[
                        '⚠️ Due to resource costs, users must be logged in to access projects.',
                        html.Br(),
                        'You can log in by clicking on any project link below or by clicking the Login button.',
                    ],
                ),
                html.Div(
                    html.P(
                        '🔒 Authentication is required to access protected data pages.'
                    ),
                    className='text-muted',
                ),
                html.Div(
                    id='auth-banner', className='mb-4'
                ),  # Dynamic auth banner here
            ],
        ),
    ],
)


@dash.callback(Output('auth-banner', 'children'), Input('url', 'pathname'))
def update_auth_banner(_):
    user = session.get('user', None)
    try:
        if 'user' in session:

            user = session['user']
            approved = user.get('custom:approved', 'false').lower()
            if approved != 'true':
                # Pending approval banner + logout button
                return html.Div(
                    [
                        html.Div(
                            className='alert alert-warning',
                            children=[
                                '⏳ You are logged in, but your account is pending admin approval.',
                                html.Br(),
                                'Please wait until an admin activates your account.',
                            ],
                        ),
                        html.H2('Available Projects', className='h4 mt-4 mb-3'),
                        build_project_section(user),
                        html.A(
                            'Logout',
                            href='/logout',
                            className='btn btn-danger',
                            role='button',
                        ),
                    ]
                )
            else:
                # Approved user - show logout button + welcome message
                return html.Div(
                    [
                        html.Div(
                            className='alert alert-success',
                            children=[
                                '✅ You are logged in.',
                                html.Br(),
                                'Have fun exploring the available projects!',
                            ],
                        ),
                        html.H2('Available Projects', className='h4 mt-4 mb-3'),
                        build_project_section(user),
                        html.A(
                            'Logout',
                            href='/logout',
                            className='btn btn-danger',
                            role='button',
                        ),
                    ]
                )
    except RuntimeError:
        # Happens when session not accessible
        pass

    # Not logged in: show login/signup buttons
    return html.Div(
        [
            html.H2('Available Projects', className='h4 mt-4 mb-3'),
            build_project_section(user),
            html.A(
                'Login',
                href='/login',
                className='btn btn-primary me-2',
                role='button',
            ),
        ]
    )
