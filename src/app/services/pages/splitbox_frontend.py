import logging
from typing import Optional
from urllib.parse import urlparse

import dash
import dash_bootstrap_components as dbc
import requests
from dash import callback, callback_context, dcc, html
from dash.dependencies import Input, Output, State
from flask import session

from app.services.utils.file_utils import (
    card_style,
    get_allowed_folders_for_user,
    get_current_username,
    list_files_in_s3,
    render_file_preview,
    s3_client,
    upload_files_to_s3,
)
from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)

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
                    'SplitBox aims at working on beatbox sound files, and split them into track for music production.',
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


@callback(Output('splitbox-auth-banner', 'children'), Input('url', 'pathname'))
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
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H2(
                                                'Select a file to work on:',
                                                className='fw-bold mb-3',
                                            ),
                                            html.P(
                                                'Your inputs/ ouputs/ folders are yours only.'
                                            ),
                                            html.P(
                                                'Everything in the shared folder is shared between all the splitbox members!'
                                            ),
                                            html.Hr(),
                                            html.Div(
                                                style={
                                                    'display': 'flex',
                                                    'gap': '40px',
                                                    'alignItems': 'flex-start',
                                                    'flexWrap': 'wrap',
                                                },
                                                children=[
                                                    # Left column: Folder choice + tags + upload button
                                                    html.Div(
                                                        style={
                                                            'flex': '1 1 300px',  # flex-grow, flex-shrink, flex-basis
                                                            'minWidth': '250px',
                                                            'maxWidth': '100%',
                                                            'display': 'flex',
                                                            'flexDirection': 'column',
                                                            'gap': '10px',
                                                        },
                                                        children=[
                                                            # Existing folder selection or new folder
                                                            html.H3(
                                                                'Upload from your device:',
                                                                className='fw-bold mb-3',
                                                            ),
                                                            html.Label(
                                                                'Select folder to save or create a new one:'
                                                            ),
                                                            dcc.Dropdown(
                                                                id='splitbox-save-folder-selector',
                                                                options=[],  # will be filled dynamically
                                                                placeholder='Select folder',
                                                                clearable=True,
                                                                style={
                                                                    'width': '100%',
                                                                    'maxWidth': '300px',  # cap the width on large screens
                                                                },
                                                            ),
                                                            dcc.Input(
                                                                id='splitbox-new-folder-name',
                                                                type='text',
                                                                placeholder='Or enter new folder name',
                                                                style={
                                                                    'width': '100%',
                                                                    'maxWidth': '300px',  # cap the width on large screens
                                                                },
                                                            ),
                                                            # Tags input
                                                            html.Label(
                                                                'Add tags for the file (comma separated):'
                                                            ),
                                                            dcc.Input(
                                                                id='splitbox-file-tags',
                                                                type='text',
                                                                placeholder='tag1, tag2, ...',
                                                                style={
                                                                    'width': '100%',
                                                                    'maxWidth': '300px',  # cap the width on large screens
                                                                },
                                                            ),
                                                            # Upload button below folder and tags
                                                            dcc.Upload(
                                                                id='splitbox-upload-file',
                                                                children=html.Button(
                                                                    'Upload your beatbox file here',
                                                                    id='upload-button',
                                                                ),
                                                                multiple=False,
                                                            ),
                                                            html.Div(
                                                                id='splitbox-upload-status'
                                                            ),
                                                        ],
                                                    ),
                                                    # Right column: Folder selector + file selector (for processing)
                                                    html.Div(
                                                        style={
                                                            'flex': '2 1 300px',
                                                            'minWidth': '250px',
                                                            'maxWidth': '100%',
                                                            'display': 'flex',
                                                            'flexDirection': 'column',
                                                            'gap': '10px',
                                                        },
                                                        children=[
                                                            html.H3(
                                                                'Or load a saved file:',
                                                                className='fw-bold mb-3',
                                                            ),
                                                            html.Label(
                                                                'Select a splitbox folder:'
                                                            ),
                                                            dcc.Dropdown(
                                                                id='splitbox-folder-selector',
                                                                options=[],
                                                                placeholder='Select a folder',
                                                                clearable=True,
                                                                style={
                                                                    'width': '100%',
                                                                    'maxWidth': '500px',  # cap the width on large screens
                                                                },
                                                            ),
                                                            html.Label(
                                                                'Select an audio file to work on:'
                                                            ),
                                                            dcc.Dropdown(
                                                                id='splitbox-file-selector',
                                                                placeholder='Select a file',
                                                                style={
                                                                    'width': '100%',
                                                                    'maxWidth': '600px',  # cap the width on large screens
                                                                },
                                                                clearable=True,
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                            html.Br(),
                                            html.Label(
                                                '📂 File Preview:',
                                                style={'fontWeight': 'bold'},
                                            ),
                                            html.Div(id='splitbox-file-display'),
                                            html.Br(),
                                        ]
                                    ),
                                    className='mb-3',
                                    style=card_style,
                                ),
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.H2(
                                                'Process the file with splitbox and observe the outputs:',
                                                className='fw-bold mb-3',
                                            ),
                                            html.Hr(),
                                            html.Label(
                                                'Click on the button to run the track splitter on the selected file:',
                                                style={'fontWeight': 'bold'},
                                            ),
                                            html.Br(),
                                            html.Button(
                                                'Split your track',
                                                id='run-splitbox-btn',
                                                n_clicks=0,
                                                style={'marginTop': '10px'},
                                            ),
                                            html.Br(),
                                            dcc.Loading(
                                                id='loading-splitbox',
                                                type='circle',  # "circle", "dot", or "default"
                                                children=html.Div(
                                                    id='splitbox-results'
                                                ),
                                            ),
                                            html.Br(),
                                        ]
                                    ),
                                    className='mb-3',
                                    style=card_style,
                                ),
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
            dbc.Button(
                '🏠 Back to Home',
                href='/',  # your home page path
                color='primary',
                className='me-2',
            ),
        ]
    )


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


@callback(
    Output('splitbox-upload-status', 'children'),
    Output('splitbox-save-folder-selector', 'options'),
    Output('splitbox-save-folder-selector', 'value'),
    Output('splitbox-folder-selector', 'options'),
    Output('splitbox-folder-selector', 'value'),
    Output('splitbox-file-selector', 'options'),
    Output('splitbox-file-selector', 'value'),
    Input('splitbox-upload-file', 'contents'),
    Input('splitbox-folder-selector', 'value'),  # folder change
    Input('url', 'pathname'),  # page load trigger
    State('splitbox-upload-file', 'filename'),
    State('splitbox-save-folder-selector', 'value'),
    State('splitbox-new-folder-name', 'value'),
    State('splitbox-file-tags', 'value'),
)
def splitbox_main_callback(
    file_content,
    folder_trigger_value,
    pathname,
    filename,
    selected_save_folder,
    new_folder_name,
    file_tags,
):
    triggered_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    bucket_name = 'splitbox-bucket'
    status_msg = ''

    username = get_current_username(session)
    folders = get_allowed_folders_for_user(session, s3_client, bucket_name)
    folder_options = [
        {
            'label': (
                f.replace(f'{username}/', '') if f.startswith(f'{username}/') else f
            ),
            'value': f,
        }
        for f in folders
    ]

    # --- Default selections ---
    folder_value = (
        folder_trigger_value
        if folder_trigger_value is not None
        else (folder_options[0]['value'] if folder_options else '')
    )
    save_folder_value = (
        selected_save_folder
        if selected_save_folder is not None
        else (folder_options[0]['value'] if folder_options else '')
    )

    # --- Populate file dropdown for selected folder ---
    file_options = []
    file_value = None
    if folder_value:
        file_options = list_files_in_s3(s3_client, bucket_name, folder_value)
        file_value = file_options[0]['value'] if file_options else None

    # --- Handle upload ---
    if triggered_id == 'splitbox-upload-file' and file_content and filename:

        if new_folder_name:
            # Always create new folders in the user's namespace unless shared is selected
            if selected_save_folder == 'shared/':
                folder_name = f'shared/{new_folder_name.strip()}'
            else:
                folder_name = f'{username}/inputs/{new_folder_name.strip()}'
        else:
            # If no new folder, use the selected folder if allowed
            folder_name = (
                selected_save_folder if selected_save_folder else f'{username}/inputs'
            )

        # --- Parse tags safely ---
        tags_list = (
            [tag.strip() for tag in file_tags.split(',') if tag.strip()]
            if file_tags
            else []
        )

        try:
            _, _, uploaded_files = upload_files_to_s3(
                s3_client,
                bucket_name,
                [file_content],
                [filename],
                folder_name,
                tags_list,
            )
        except Exception as e:
            return (
                f'Error uploading file: {e}',
                folder_options,
                save_folder_value,
                folder_options,
                folder_value,
                file_options,
                file_value,
            )

        status_msg = f"File '{filename}' uploaded successfully to '{folder_name}'"

        # --- Update folder dropdowns with new folder ---
        if folder_name not in [o['value'] for o in folder_options]:
            folder_options.append({'label': folder_name, 'value': folder_name})

        folder_value = folder_name
        save_folder_value = folder_name

        # --- Refresh file dropdown with all files in that folder ---
        file_options = list_files_in_s3(s3_client, bucket_name, folder_name)
        file_value = next(
            (f['value'] for f in file_options if f['label'] == filename), None
        )

    return (
        status_msg,
        folder_options,
        save_folder_value,
        folder_options,
        folder_value,
        file_options,
        file_value,
    )
