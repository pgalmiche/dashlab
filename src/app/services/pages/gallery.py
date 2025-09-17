import logging
import os

import dash
import dash_bootstrap_components as dbc
from dash import ALL, callback, ctx, dcc, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from flask import session

from app.services.utils.file_utils import (
    build_gallery_layout,
    delete_file_from_s3,
    filter_files_by_type,
    get_s3_client,
    list_all_files,
    list_s3_folders,
    upload_files_to_s3,
)
from app.services.utils.ui_utils import bucket_dropdown
from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)

if settings.env != 'testing':
    dash.register_page(__name__, path='/gallery', name='Gallery', order=2)


layout = html.Div(
    children=[
        dcc.Location(id='url', refresh=False),  # Needed to trigger callback
        html.Div(
            className='container py-5',
            children=[
                html.H1('Welcome to the Gallery 👋', className='fw-bold mb-3'),
                html.P(
                    'Displays buckets content for an overview of the files for faster navigation.',
                    className='lead',
                ),
                html.Div(
                    id='gallery-auth-banner', className='mb-4'
                ),  # Dynamic auth banner here
            ],
        ),
    ],
)


@callback(Output('gallery-auth-banner', 'children'), Input('url', 'pathname'))
def update_auth_banner(_):
    try:
        if 'user' in session:

            user = session['user']
            approved = user.get('custom:approved', 'false').lower()

            if approved != 'true':
                # Pending approval banner + logout button
                return html.Div(
                    [
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
            else:
                # Approved user - show logout button + welcome message
                return html.Div(
                    [
                        html.Div(
                            className='alert alert-success',
                            children=[
                                '✅ You are logged in.',
                                html.Br(),
                                'Enjoy the navigation!',
                            ],
                        ),
                        html.Div(
                            children=[
                                html.H2('S3 File Gallery 📸'),
                                html.Div(
                                    [
                                        # Hidden store to trigger page load
                                        dcc.Store(
                                            id='gallery-page-load-trigger', data=True
                                        ),
                                        # Bucket selection
                                        dbc.Row(
                                            [
                                                dbc.Label(
                                                    'Select Bucket:',
                                                    width=4,
                                                    className='fw-bold',
                                                ),
                                                dbc.Col(
                                                    bucket_dropdown(
                                                        layout_id='gallery-bucket-selector'
                                                    ),
                                                    width=8,
                                                ),
                                            ],
                                            className='mb-3 align-items-center',
                                        ),
                                        # Target folder selection / creation
                                        dbc.Row(
                                            [
                                                dbc.Label(
                                                    'Select / Create Folder:',
                                                    width=4,
                                                    className='fw-bold',
                                                ),
                                                dbc.Col(
                                                    [
                                                        dcc.Dropdown(
                                                            id='gallery-folder-dropdown',
                                                            options=[],  # filled dynamically
                                                            placeholder='Select existing folder',
                                                            searchable=True,
                                                            clearable=True,
                                                            style={
                                                                'marginBottom': '5px'
                                                            },
                                                        ),
                                                        dcc.Input(
                                                            id='gallery-new-folder-input',
                                                            type='text',
                                                            placeholder='Or type a new folder name',
                                                            style={'width': '100%'},
                                                        ),
                                                    ],
                                                    width=8,
                                                ),
                                            ],
                                            className='mb-3 align-items-center',
                                        ),
                                        # File type selection
                                        dbc.Row(
                                            [
                                                dbc.Label(
                                                    'Select File Type:',
                                                    width=4,
                                                    className='fw-bold',
                                                ),
                                                dbc.Col(
                                                    dcc.Dropdown(
                                                        id='type-dropdown',
                                                        options=[
                                                            {
                                                                'label': 'Images',
                                                                'value': 'image',
                                                            },
                                                            {
                                                                'label': 'PDFs',
                                                                'value': 'pdf',
                                                            },
                                                            {
                                                                'label': 'Audio',
                                                                'value': 'audio',
                                                            },
                                                            {
                                                                'label': 'Video',
                                                                'value': 'video',
                                                            },
                                                            {
                                                                'label': 'Text',
                                                                'value': 'text',
                                                            },
                                                        ],
                                                        value='image',
                                                        clearable=False,
                                                    ),
                                                    width=8,
                                                ),
                                            ],
                                            className='mb-3 align-items-center',
                                        ),
                                    ],
                                    style={
                                        'maxWidth': '600px',
                                        'padding': '15px',
                                        'border': '1px solid #dee2e6',
                                        'borderRadius': '8px',
                                        'backgroundColor': '#f8f9fa',
                                    },
                                ),
                                html.Hr(),
                                html.Div(
                                    [
                                        html.H5('Upload Files to Selected Folder:'),
                                        dcc.Upload(
                                            id='gallery-upload-files',
                                            children=dbc.Button(
                                                [
                                                    html.I(
                                                        className='bi bi-upload me-2'
                                                    ),  # Bootstrap icon
                                                    'Select Files',
                                                ],
                                                color='primary',
                                                outline=False,
                                                size='lg',
                                                className='d-flex align-items-center',
                                            ),
                                            multiple=True,
                                        ),
                                        dcc.Store(
                                            id='gallery-presigned-data',
                                            storage_type='memory',
                                        ),
                                        html.Div(id='gallery-rename-files-container'),
                                        html.Br(),
                                        html.Br(),
                                        dbc.Button(
                                            id='confirm-upload-btn',
                                            children=[
                                                html.I(
                                                    className='bi bi-upload me-2'
                                                ),  # Bootstrap icon
                                                'Upload Renamed Files',
                                            ],
                                            color='primary',
                                            outline=False,
                                            size='lg',
                                            className='d-flex align-items-center',
                                        ),
                                        html.Div(
                                            id='gallery-upload-status',
                                            style={'marginTop': '10px'},
                                        ),
                                    ]
                                ),
                                html.Hr(),
                                html.Div(
                                    id='bucket-gallery-container'
                                ),  # This will hold the dynamic gallery
                                html.Div(id='delete-status'),
                            ],
                        ),
                    ]
                )

    except RuntimeError:
        # Happens when session not accessible
        pass

    # Not logged in: show login/signup buttons
    return html.Div(
        [
            html.Div(
                className='alert alert-info',
                children=[
                    '⚠️ Due to resource costs, users must be logged in to access projects.',
                    html.Br(),
                    'You can log in by clicking on any project link below or by clicking the Login button.',
                ],
            ),
            html.Div(
                html.P('🔒 Authentication is required to access protected data pages.'),
                className='text-muted',
            ),
            html.P('Browse the default gallery:', className='lead'),
            # Hidden store to trigger page load
            dcc.Store(id='gallery-page-load-trigger', data=True),
            # Default gallery container
            html.Div(id='default-gallery-container'),
            html.Br(),
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
    Output('gallery-bucket-selector', 'options'),
    Output('gallery-bucket-selector', 'value'),
    Input('gallery-page-load-trigger', 'data'),
)
def populate_gallery_bucket_dropdown(pathname):
    """Populate bucket dropdown dynamically based on user session."""
    if 'user' not in session:
        raise PreventUpdate

    buckets = session.get('ALLOWED_BUCKETS', {'dashlab-bucket': 'us-east-1'})
    default = session.get('DEFAULT_BUCKET')

    options = [{'label': b, 'value': b} for b in buckets.keys()]

    # Pick first bucket if default is not set or invalid
    if not default or default not in buckets:
        default = list(buckets.keys())[0] if buckets else None

    # Ensure a value is always returned
    return options, default


@callback(
    Output('gallery-folder-dropdown', 'options'),
    Input('gallery-bucket-selector', 'value'),
)
def refresh_folder_options(gallery_bucket):
    folders = list_s3_folders(get_s3_client(gallery_bucket), gallery_bucket)
    options = [{'label': f or '(root)', 'value': f} for f in folders]
    return options


@callback(
    Output('bucket-gallery-container', 'children'),
    Output('delete-status', 'children'),
    Input('confirm-upload-btn', 'n_clicks'),
    Input({'type': 'delete-file-btn', 'file_key': ALL}, 'n_clicks'),
    State('gallery-upload-files', 'contents'),
    State('gallery-upload-files', 'filename'),
    State({'type': 'rename-file', 'index': ALL}, 'value'),
    Input('gallery-folder-dropdown', 'value'),
    State('gallery-new-folder-input', 'value'),
    Input('gallery-bucket-selector', 'value'),
    Input('type-dropdown', 'value'),
    prevent_initial_call=True,
)
def manage_gallery(
    n_upload,
    delete_clicks,
    upload_contents,
    original_filenames,
    renamed_filenames,
    folder,
    new_folder_name,
    bucket_name,
    file_type,
):
    triggered = ctx.triggered_id
    delete_status = ''

    client = get_s3_client(bucket_name)

    # --- Handle deletion ---
    if isinstance(triggered, dict) and triggered.get('type') == 'delete-file-btn':
        file_key = triggered['file_key']
        delete_file_from_s3(client, bucket_name, file_key)
        delete_status = f'Deleted {file_key}'

    # --- Handle upload ---
    elif triggered == 'confirm-upload-btn' and upload_contents:
        filenames_to_upload = original_filenames
        if renamed_filenames and len(renamed_filenames) == len(original_filenames):
            filenames_to_upload = [
                f'{new}{os.path.splitext(orig)[1]}'
                for orig, new in zip(original_filenames, renamed_filenames)
            ]

        target_folder = None
        if new_folder_name and new_folder_name.strip():
            target_folder = new_folder_name.strip()
        elif folder:  # selected folder from dropdown
            target_folder = folder
        else:
            target_folder = ''  # fallback to root

        _, _, _ = upload_files_to_s3(
            client,
            bucket_name,
            upload_contents,
            filenames_to_upload,
            target_folder,
        )

    # --- Refresh gallery ---
    all_files = list_all_files(client, bucket_name, folder)
    filtered_files = filter_files_by_type(all_files, file_type)
    gallery_div = build_gallery_layout(
        client, bucket_name, filtered_files, show_delete=True
    )

    return gallery_div, delete_status


@callback(
    Output('gallery-rename-files-container', 'children'),
    Input('gallery-upload-files', 'filename'),
    prevent_initial_call=True,
)
def show_rename_inputs(filenames):
    if not filenames:
        raise PreventUpdate

    return html.Div(
        [
            dbc.Row(
                [
                    # Label with fixed width and more space
                    dbc.Label(
                        f"Rename '{os.path.splitext(f)[0]}':",  # only filename
                        width=3,
                        style={'whiteSpace': 'nowrap', 'marginRight': '15px'},
                    ),
                    dbc.Col(
                        dbc.Input(
                            id={'type': 'rename-file', 'index': i},
                            value=os.path.splitext(f)[0],  # prefill without extension
                            type='text',
                            style={'width': '100%', 'minWidth': '250px'},
                        ),
                        width=9,
                    ),
                ],
                className='mb-3',  # more space between rows
                align='center',
            )
            for i, f in enumerate(filenames)
        ],
        style={'maxHeight': '400px', 'overflowY': 'auto'},  # scroll if many files
    )


@callback(
    Output('gallery-upload-folder-dropdown', 'options'),
    Input('gallery-bucket-selector', 'value'),
)
def populate_upload_folder_options(bucket_name):
    folders = list_s3_folders(get_s3_client(bucket_name), bucket_name)
    return [{'label': f or '(root)', 'value': f} for f in folders]


@callback(
    Output('default-gallery-container', 'children'),
    Input('gallery-page-load-trigger', 'data'),
)
def show_default_gallery(_):
    # Always show dashlab-bucket for non-logged-in users
    bucket_name = 'dashlab-bucket'
    folder = ''  # root
    file_type = 'image'  # default, can adjust

    all_files = list_all_files(get_s3_client(bucket_name), bucket_name, folder)
    filtered_files = filter_files_by_type(all_files, file_type)
    gallery_div = build_gallery_layout(
        get_s3_client(bucket_name), bucket_name, filtered_files
    )
    return gallery_div


@callback(
    Output('gallery-presigned-data', 'data'),  # store only
    Input('confirm-upload-btn', 'n_clicks'),
    State('gallery-upload-files', 'filename'),
    State('gallery-folder-dropdown', 'value'),
    State('gallery-new-folder-input', 'value'),
    State('gallery-bucket-selector', 'value'),
    prevent_initial_call=True,
)
def get_presigned_uploads(n_clicks, filenames, folder, new_folder, bucket_name):
    if not filenames:
        raise PreventUpdate
    target_folder = new_folder or folder or ''
    s3_client = get_s3_client(bucket_name)

    from app.services.utils.file_utils import generate_presigned_uploads

    presigned_posts = generate_presigned_uploads(
        s3_client, bucket_name, filenames, target_folder
    )
    return presigned_posts  # store only


dash_clientside_callback = dash.clientside_callback

dash_clientside_callback(
    """
    function(presignedData, fileContents, filenames) {
        if (!presignedData || !fileContents || !filenames) return '';

        presignedData.forEach((data, idx) => {
            const fileContent = fileContents[idx];
            const byteString = atob(fileContent.split(',')[1]);
            const arrayBuffer = new ArrayBuffer(byteString.length);
            const uintArray = new Uint8Array(arrayBuffer);
            for (let i = 0; i < byteString.length; i++) {
                uintArray[i] = byteString.charCodeAt(i);
            }
            const blob = new Blob([uintArray], { type: 'application/octet-stream' });

            const formData = new FormData();
            Object.entries(data.presigned_post.fields).forEach(([k,v]) => {
                formData.append(k, v);
            });
            formData.append('file', blob, data.filename);

            fetch(data.presigned_post.url, {
                method: 'POST',
                body: formData
            }).then(resp => {
                if (!resp.ok) console.error('Upload failed for', data.filename);
            }).catch(err => console.error(err));
        });

        return 'Files are being uploaded directly to S3!';
    }
    """,
    Output('gallery-upload-status', 'children'),
    Input('gallery-presigned-data', 'data'),
    State('gallery-upload-files', 'contents'),
    State('gallery-upload-files', 'filename'),
)
