import logging
from urllib.parse import urlparse

import dash
import dash_bootstrap_components as dbc
import requests
from dash import ALL, callback, ctx, dcc, html
from dash.dependencies import Input, Output, State
from flask import jsonify, request, session

from app.services.utils.file_utils import (
    card_style,
    delete_file_from_s3,
    get_allowed_folders_for_user,
    get_current_username,
    get_s3_client,
    get_viz_file_key,
    list_files_in_s3,
    move_file_and_update_metadata,
    render_file_preview,
    s3_client,
    s3_viz_exists,
    upload_files_to_s3,
)
from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)
logging.getLogger('pymongo').setLevel(logging.WARNING)  # only show warnings and errors

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
                                                            html.Hr(),
                                                            html.H4(
                                                                '🎤 Or record directly:',
                                                                className='fw-bold mt-3',
                                                            ),
                                                            html.Label(
                                                                'This recording will be saved in your inputs/recorded/ folder.'
                                                            ),
                                                            dcc.Input(
                                                                id='splitbox-recording-filename',
                                                                type='text',
                                                                placeholder='Recording name (no extension)',
                                                                style={
                                                                    'width': '100%',
                                                                    'maxWidth': '300px',
                                                                },
                                                            ),
                                                            # Hidden Store for username
                                                            dcc.Store(
                                                                id='splitbox-username-store',
                                                                data=get_current_username(
                                                                    session
                                                                ),  # set username from Flask session
                                                            ),
                                                            html.Button(
                                                                'Start Recording',
                                                                id='splitbox-start-recording',
                                                                n_clicks=0,
                                                                className='btn btn-secondary',
                                                            ),
                                                            html.Button(
                                                                'Stop & Upload',
                                                                id='splitbox-stop-recording',
                                                                n_clicks=0,
                                                                className='btn btn-primary',
                                                            ),
                                                            dcc.Store(
                                                                id='splitbox-uploaded-recording-key'
                                                            ),
                                                            html.Div(
                                                                id='splitbox-recording-status',
                                                                className='mt-2 text-info',
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
                                                            html.Div(
                                                                id='splitbox-delete-file-status',
                                                                className='mt-2 text-info',
                                                            ),
                                                            html.Hr(
                                                                style={
                                                                    'marginTop': '75px',
                                                                    'marginBottom': '30px',
                                                                }
                                                            ),
                                                            html.H3(
                                                                '📂 Selected File Preview:',
                                                                className='fw-bold mb-3',
                                                            ),
                                                            html.Div(
                                                                id='splitbox-file-display'
                                                            ),
                                                            html.Br(),
                                                            html.Div(
                                                                id='splitbox-delete-file-status',
                                                                className='mt-2 text-info',
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),
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
                                                'Click to analyze the selected file:',
                                                style={'fontWeight': 'bold'},
                                            ),
                                            html.Br(),
                                            dbc.Button(
                                                'Analyze file',
                                                id='run-analyze-btn',
                                                n_clicks=0,
                                                color='primary',  # Bootstrap primary color
                                                size='lg',  # large button
                                                className='mb-2',  # margin bottom
                                                style={
                                                    'width': '200px'
                                                },  # optional fixed width
                                            ),
                                            html.Br(),
                                            dcc.Loading(
                                                id='loading-analyze',
                                                type='circle',
                                                children=html.Div(
                                                    id='splitbox-analysis-results'
                                                ),
                                            ),
                                            html.Hr(),
                                            html.Label(
                                                'Click on the button to run the track splitter on the selected file:',
                                                style={'fontWeight': 'bold'},
                                            ),
                                            html.Br(),
                                            dbc.Button(
                                                [
                                                    html.I(
                                                        className='bi bi-scissors me-2'
                                                    ),
                                                    'Split your track',
                                                ],
                                                id='run-splitbox-btn',
                                                n_clicks=0,
                                                color='success',  # Green color to indicate “action”
                                                size='lg',  # Large button
                                                className='mb-3',  # Margin bottom
                                                style={
                                                    'width': '200px',  # Optional fixed width for consistency
                                                    'transition': 'all 0.2s ease-in-out',  # Smooth hover effect
                                                },
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

        username = get_current_username(session)
        output_path = f's3://splitbox-bucket/{username}/outputs/split/{file_key}/'

        params = {
            'path': f's3://splitbox-bucket/{file_key}',  # input file
            'output_path': output_path,  # where analysis results will be saved
        }

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


app = dash.get_app()

app.clientside_callback(
    """
async function(startClicks, stopClicks, filenameInput, usernameInput) {
    if (!window.splitboxRecorder) {
        window.splitboxRecorder = null;
        window.splitboxChunks = [];
        window.startClicks = 0;
        window.stopClicks = 0;
    }

    if (!filenameInput || filenameInput.trim() === "") {
        return ["❌ Please enter a recording name before starting!", null];
    }

    const username = usernameInput || "shared";
    const saveKey = `${username}/inputs/recorded/${filenameInput.trim()}.webm`;

    if (startClicks > window.startClicks) {
        window.startClicks = startClicks;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            window.splitboxRecorder = new MediaRecorder(stream);
            window.splitboxChunks = [];
            window.splitboxRecorder.ondataavailable = e => window.splitboxChunks.push(e.data);
            window.splitboxRecorder.start();
            return ["🎤 Recording started!", null];
        } catch (err) {
            return ["❌ Could not start recording: " + err.message, null];
        }
    }

    if (stopClicks > window.stopClicks && window.splitboxRecorder) {
        window.stopClicks = stopClicks;
        return new Promise((resolve) => {
            window.splitboxRecorder.onstop = async () => {
                const blob = new Blob(window.splitboxChunks, { type: "audio/webm" });
                try {
                    const resp = await fetch("/splitbox/generate-presigned-upload", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ file_key: saveKey })
                    });
                    if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
                    const data = await resp.json();
                    const uploadUrl = data.url;

                    const formData = new FormData();
                    Object.entries(uploadUrl.fields).forEach(([k,v]) => formData.append(k,v));
                    formData.append("file", blob);

                    const uploadResp = await fetch(uploadUrl.url, { method: "POST", body: formData });
                    if (!uploadResp.ok) throw new Error(`Upload failed: ${uploadResp.status}`);

                    // Return both status message and uploaded file key
                    resolve(["✅ Recording uploaded successfully!", saveKey]);
                } catch (err) {
                    resolve(["❌ Upload failed: " + err.message, null]);
                }
            };
            window.splitboxRecorder.stop();
        });
    }

    return [window.dash_clientside.no_update, null];
}
    """,
    [
        Output('splitbox-recording-status', 'children'),
        Output('splitbox-uploaded-recording-key', 'data'),
    ],
    [
        Input('splitbox-start-recording', 'n_clicks'),
        Input('splitbox-stop-recording', 'n_clicks'),
    ],
    [
        State('splitbox-recording-filename', 'value'),
        State('splitbox-username-store', 'data'),
    ],
)


@dash.get_app().server.route('/splitbox/generate-presigned-upload', methods=['POST'])
def splitbox_generate_presigned_upload():
    """
    Generate a presigned POST URL for audio recording upload
    """
    data = request.get_json()  # parse JSON from fetch
    file_key = data.get('file_key')  # get the filename from the client

    if not file_key:
        return jsonify({'error': 'file_key is required'}), 400

    presigned_post = s3_client.generate_presigned_post(
        Bucket='splitbox-bucket',
        Key=file_key,
        Fields={'Content-Type': 'audio/webm'},
        Conditions=[['starts-with', '$Content-Type', 'audio/webm']],
        ExpiresIn=300,
    )
    return jsonify({'url': presigned_post, 'file_key': file_key})


@callback(
    Output('splitbox-delete-file-status', 'children'),
    Input({'type': 'delete-file-btn', 'file_key': ALL}, 'n_clicks'),
    prevent_initial_call=True,
)
def manage_deletions(delete_clicks):
    triggered = ctx.triggered_id
    delete_status = ''
    bucket_name = 'splitbox-bucket'

    # Only proceed if a button was actually clicked
    if isinstance(triggered, dict) and triggered.get('type') == 'delete-file-btn':
        file_key = triggered['file_key']
        # Safety check: only delete if the click count > 0
        if delete_clicks[delete_clicks.index(ctx.triggered[0]['value'])] > 0:
            delete_file_from_s3(get_s3_client(bucket_name), bucket_name, file_key)
            delete_status = f'Deleted {file_key}'

    return delete_status


@callback(
    Output('splitbox-file-display', 'children'),
    Output('splitbox-upload-status', 'children'),
    Output('splitbox-save-folder-selector', 'options'),
    Output('splitbox-save-folder-selector', 'value'),
    Output('splitbox-folder-selector', 'options'),
    Output('splitbox-folder-selector', 'value'),
    Output('splitbox-file-selector', 'options'),
    Output('splitbox-file-selector', 'value'),
    Input('splitbox-upload-file', 'contents'),
    Input('splitbox-folder-selector', 'value'),
    Input('url', 'pathname'),
    Input('splitbox-uploaded-recording-key', 'data'),
    Input({'type': 'rename-file-btn', 'file_key': ALL}, 'n_clicks'),
    Input('splitbox-file-selector', 'value'),
    State('splitbox-upload-file', 'filename'),
    State('splitbox-save-folder-selector', 'value'),
    State('splitbox-new-folder-name', 'value'),
    State('splitbox-file-tags', 'value'),
    State({'type': 'rename-file-input', 'file_key': ALL}, 'value'),
    State({'type': 'move-folder-input', 'file_key': ALL}, 'value'),
)
def master_file_callback(
    upload_contents,
    folder_selector_value,
    pathname,
    uploaded_recording_key,
    rename_clicks,
    selected_file,
    upload_filename,
    save_folder_value,
    new_folder_name,
    file_tags,
    rename_new_names,
    rename_target_folders,
):
    triggered = ctx.triggered_id
    bucket_name = 'splitbox-bucket'
    username = get_current_username(session)

    status_msg = ''
    updated_preview = html.Div('No file selected.')

    # --- Get folders for dropdowns ---
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
    save_folder_value = save_folder_value or (
        folder_options[0]['value'] if folder_options else ''
    )
    folder_value = folder_selector_value or save_folder_value

    # --- Initialize file dropdown ---
    file_options = list_files_in_s3(s3_client, bucket_name, folder_value)
    file_value = (
        selected_file
        if selected_file
        else (file_options[0]['value'] if file_options else None)
    )

    # --- Handle mic recording upload ---
    if triggered == 'splitbox-uploaded-recording-key' and uploaded_recording_key:
        status_msg = f'🎤 Recording uploaded successfully: {uploaded_recording_key}'
        folder_name = f'{username}/inputs'
        if folder_name not in [o['value'] for o in folder_options]:
            folder_options.append({'label': folder_name, 'value': folder_name})
        folder_value = save_folder_value = folder_name
        file_options = list_files_in_s3(s3_client, bucket_name, folder_name)
        file_value = uploaded_recording_key

    # --- Handle file upload ---
    elif triggered == 'splitbox-upload-file' and upload_contents and upload_filename:
        if new_folder_name:
            folder_name = (
                f'shared/{new_folder_name.strip()}'
                if save_folder_value == 'shared/'
                else f'{username}/inputs/{new_folder_name.strip()}'
            )
        else:
            folder_name = save_folder_value or f'{username}/inputs/'
        tags_list = [tag.strip() for tag in (file_tags or '').split(',') if tag.strip()]
        try:
            _, _, uploaded_files = upload_files_to_s3(
                s3_client,
                bucket_name,
                [upload_contents],
                [upload_filename],
                folder_name,
                tags_list,
            )
            status_msg = (
                f"File '{upload_filename}' uploaded successfully to '{folder_name}'"
            )
            if folder_name not in [o['value'] for o in folder_options]:
                folder_options.append({'label': folder_name, 'value': folder_name})
            folder_value = save_folder_value = folder_name
            file_options = list_files_in_s3(s3_client, bucket_name, folder_name)
            file_value = next(
                (f['value'] for f in file_options if f['label'] == upload_filename),
                None,
            )
        except Exception as e:
            status_msg = f'Error uploading file: {e}'

    # --- Handle file rename/move ---
    elif isinstance(triggered, dict) and triggered.get('type') == 'rename-file-btn':
        idx = [
            i
            for i, ck in enumerate(ctx.inputs_list[4])
            if ck['id']['file_key'] == triggered['file_key']
        ][0]
        new_name = (
            rename_new_names[idx]
            if rename_new_names and rename_new_names[idx]
            else None
        )
        target_folder = rename_target_folders[idx] if rename_target_folders else None
        file_key_to_move = triggered['file_key']
        result = move_file_and_update_metadata(
            s3_client,
            bucket_name,
            file_key_to_move,
            new_tags=file_tags,
            target_folder=target_folder,
            new_name=new_name,
        )
        status_msg = result

    # --- Refresh files in current folder ---
    file_options = list_files_in_s3(s3_client, bucket_name, folder_value)
    file_value = file_value or (file_options[0]['value'] if file_options else None)

    # --- Render file preview ---
    if file_value:
        display_component, _, _, _ = render_file_preview(
            s3_client, bucket_name, file_value, show_delete=True
        )
        updated_preview = html.Div([display_component])

    return (
        updated_preview,
        status_msg,
        folder_options,
        save_folder_value,
        folder_options,
        folder_value,
        file_options,
        file_value,
    )


@callback(
    Output('splitbox-analysis-results', 'children'),
    Output('run-analyze-btn', 'disabled'),
    Input('splitbox-file-selector', 'value'),
    Input('run-analyze-btn', 'n_clicks'),
)
def show_or_run_analysis(file_key, n_clicks):
    client = get_s3_client('splitbox-bucket')
    username = get_current_username(session)

    if not file_key:
        return html.Div('Please select a file.'), False

    triggered = ctx.triggered
    triggered_id = triggered[0]['prop_id'].split('.')[0] if triggered else None

    # --- Show existing analysis when file is selected ---
    if triggered_id == 'splitbox-file-selector':
        if s3_viz_exists(client, 'splitbox-bucket', file_key, username=username):
            viz_key = get_viz_file_key(file_key, username=username)
            preview_component, *_ = render_file_preview(
                client,
                bucket_name='splitbox-bucket',
                file_key=viz_key,
                show_download=True,
                show_delete=True,
                allow_rename=False,
            )
            return preview_component, False
        else:
            return (
                html.Div(
                    '⚠️ No analysis done yet. Click the button to generate one.',
                    style={'padding': '20px', 'color': '#666', 'textAlign': 'center'},
                ),
                False,
            )

    # --- Run analysis if button clicked ---
    elif triggered_id == 'run-analyze-btn' and n_clicks > 0:
        try:
            output_path = (
                f's3://splitbox-bucket/{username}/outputs/{file_key}/analysis/'
            )
            resp = requests.get(
                'http://splitbox-api-prod:8888/analyze',
                params={
                    'path': f's3://splitbox-bucket/{file_key}',
                    'output_path': output_path,
                },
                timeout=300,
            )
            if resp.status_code != 200:
                return html.Div(f'❌ Error {resp.status_code}: {resp.text}'), False

            data = resp.json()
            plot_file = data.get('plot_file')
            if not plot_file:
                return html.Div('⚠️ No plot file returned.'), False

            bucket = plot_file.split('/')[2]
            key = '/'.join(plot_file.split('/')[3:])
            preview_component, *_ = render_file_preview(
                client,
                bucket_name=bucket,
                file_key=key,
                show_download=True,
                show_delete=True,
                allow_rename=False,
            )
            return preview_component, False
        except Exception as e:
            return html.Div(f'⚠️ Error running analysis: {str(e)}'), False

    return html.Div('⚠️ Unexpected state'), False
