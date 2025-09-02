import dash
from dash import Input, Output, dcc, html
from flask import session

from config.settings import settings  # Adjust import if your settings are elsewhere

if settings.env != 'testing':
    dash.register_page(__name__, path='/splitbox', name='SplitBox', order=2)

layout = html.Div(
    children=[
        dcc.Location(id='url', refresh=False),  # Needed to trigger callback
        html.Div(
            className='container py-5',
            children=[
                html.H1('Welcome to SplitBox 👋', className='fw-bold mb-3'),
                html.P(
                    'SplitBox aims at working on beatbox sound files!',
                    className='lead',
                ),
                html.P(
                    [
                        '📘 Full project documentation is available on the ',
                        html.A(
                            'GitLab Page of Mickael Bestard',
                            href='https://mickael.bestard.gitlab.io/splitbox/',
                            target='_blank',
                            className='text-primary',
                        ),
                        '.',
                        html.Br(),
                        '🧑‍💻 You can also explore the codebase and CI/CD pipelines on ',
                        html.A(
                            'GitLab',
                            href='https://gitlab.com/mickael.bestard/splitbox',
                            target='_blank',
                            className='text-primary',
                        ),
                        '.',
                        html.Br(),
                        html.Br(),
                        "🛠️ To explore how we worked with Mickael on this project and learn more about its dependencies, don't hesitate to visit my wiki: ",
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
                    id='splitbox-auth-banner', className='mb-4'
                ),  # Dynamic auth banner here
            ],
        ),
    ],
)


@dash.callback(Output('splitbox-auth-banner', 'children'), Input('url', 'pathname'))
def update_auth_banner(_):
    try:
        if 'user' in session:

            user = session['user']
            approved = user.get('custom:approved', 'false').lower()
            splitbox_user = user.get('custom:splitbox-access', 'false').lower()

            if approved != 'true' and splitbox_user != 'true':
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
                        html.A(
                            'Logout',
                            href='/logout',
                            className='btn btn-danger',
                            role='button',
                        ),
                    ]
                )
            elif splitbox_user != 'true':
                # Pending approval banner + logout button
                return html.Div(
                    [
                        html.Div(
                            className='alert alert-warning',
                            children=[
                                '⏳ You are logged in and approved, but not a splitbox member!',
                                html.Br(),
                                'Please ask for membership wait until an admin changes that.',
                            ],
                        ),
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
                                '✅ You are logged in and a member of SplitBox!',
                                html.Br(),
                                'Enjoy the app, Beatboxer!',
                            ],
                        ),
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
            html.A(
                'Login',
                href='/login',
                className='btn btn-primary me-2',
                role='button',
            ),
        ]
    )
