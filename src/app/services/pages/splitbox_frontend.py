import logging
from typing import Optional
from urllib.parse import urlparse

import boto3
import dash
import requests
from dash import callback, dcc, html
from dash.dependencies import Input, Output, State
from flask import session

from app.services.utils.file_utils import (
    list_files_in_s3,
    list_s3_folders,
    render_file_preview,
)
from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)

if settings.env != 'testing':
    dash.register_page(__name__, path='/splitbox', name='SplitBox', order=2)

AWS_REGION = 'us-east-1'
# Initialize boto3 S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=AWS_REGION,
)

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
                        html.Div(
                            children=[
                                html.Label('Select a splitbox folder:'),
                                dcc.Dropdown(
                                    id='splitbox-folder-selector',
                                    options=[],
                                    placeholder='Select a folder',
                                    clearable=True,
                                    style={'width': '300px'},
                                ),
                                html.Br(),
                                html.Label('Select an audio file to work on:'),
                                dcc.Dropdown(
                                    id='splitbox-file-selector',
                                    placeholder='Select a file',
                                    style={'width': '600px'},
                                    clearable=True,
                                ),
                                html.Br(),
                                html.Label(
                                    '📂 File Preview:', style={'fontWeight': 'bold'}
                                ),
                                html.Div(id='splitbox-file-display'),
                                html.Br(),
                                html.Label(
                                    'Click on the button to run the track splitter on the selected file:',
                                    style={'fontWeight': 'bold'},
                                ),
                                html.Br(),
                                html.Button(
                                    'Launch SplitBox',
                                    id='run-splitbox-btn',
                                    n_clicks=0,
                                    style={'marginTop': '10px'},
                                ),
                                html.Br(),
                                dcc.Loading(
                                    id='loading-splitbox',
                                    type='circle',  # "circle", "dot", or "default"
                                    children=html.Div(id='splitbox-results'),
                                ),
                                html.Br(),
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


@callback(
    Output('splitbox-folder-selector', 'options'),
    Input('url', 'pathname'),  # trigger when page loads
)
def refresh_splitbox_folder_options(_):
    """
    Refresh the folder options for the splitbox bucket.
    The bucket is fixed, so we ignore the input value.
    """
    # List folders in the fixed bucket
    folders = list_s3_folders(s3_client, 'splitbox-bucket')

    # Convert to Dropdown options
    options = [{'label': f or '(root)', 'value': f} for f in folders]

    return options


@callback(
    Output('splitbox-file-selector', 'options'),
    Input('splitbox-folder-selector', 'value'),
)
def update_file_selector_options(folder_name: Optional[str]):
    return list_files_in_s3(s3_client, 'splitbox-bucket', folder_name)


@callback(
    Output('splitbox-file-display', 'children'),
    Input('splitbox-file-selector', 'value'),
)
def display_selected_file(file_key: Optional[str]):
    if not file_key:
        return html.Div('No file selected.'), '', None, ''

    display_component, _, _, _ = render_file_preview(
        s3_client, 'splitbox-bucket', file_key
    )
    return display_component


def render_audio_players_with_download(audio_urls):
    audio_divs = []
    for i, url in enumerate(audio_urls):
        parsed = urlparse(url)
        # Remove leading slash
        path_parts = parsed.path.lstrip('/').split('/')

        # Display the full key path
        display_path = '/' + '/'.join(path_parts)

        audio_divs.append(
            html.Div(
                [
                    html.Label(f'Track {i+1}: {display_path}'),
                    html.Audio(src=url, controls=True, style={'width': '100%'}),
                    html.Br(),
                    html.A(
                        '⬇ Download',
                        href=url,
                        target='_blank',
                        style={'marginTop': '5px', 'display': 'inline-block'},
                    ),
                ],
                style={
                    'marginBottom': '15px',
                    'padding': '5px',
                    'border': '1px solid #ddd',
                    'borderRadius': '5px',
                },
            )
        )

    return html.Div(audio_divs, style={'maxWidth': '600px', 'margin': '0 auto'})


@callback(
    Output('splitbox-results', 'children'),
    Output('run-splitbox-btn', 'disabled'),
    Input('run-splitbox-btn', 'n_clicks'),
    State('splitbox-file-selector', 'value'),
    prevent_initial_call=True,
)
def run_splitbox(n_clicks, file_key):
    if not file_key or n_clicks <= 0:
        return html.Div('Please select a file and click Run.'), False

    try:
        # Disable button while processing
        url = 'http://splitbox-api-prod:8888/split_sources'
        params = {'path': f's3://splitbox-bucket/{file_key}'}

        resp = requests.get(url, params=params, timeout=300)
        if resp.status_code != 200:
            return html.Div(f'❌ Error {resp.status_code}: {resp.text}'), False

        data = resp.json()
        audio_urls = data.get('files', [])
        if not audio_urls:
            return html.Div('⚠️ No output files returned.'), False

        # Render audio players
        results_component = render_audio_players_with_download(audio_urls)
        return results_component, False  # re-enable button

    except Exception as e:
        return html.Div(f'⚠️ Error running SplitBox: {str(e)}'), False
