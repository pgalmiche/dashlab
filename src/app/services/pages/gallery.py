import logging

import dash
import dash_bootstrap_components as dbc
from dash import ALL, callback, ctx, dcc, html
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
from flask import session

from app.services.utils.file_utils import (
    build_gallery_layout,
    delete_file_from_s3,
    filter_files_by_type,
    list_all_files,
    list_s3_folders,
    s3_client,
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
                                        dcc.Store(
                                            id='gallery-page-load-trigger', data=True
                                        ),
                                        html.Label('Select Bucket:'),
                                        bucket_dropdown(
                                            layout_id='gallery-bucket-selector'
                                        ),
                                        html.Label('Select Folder:'),
                                        dcc.Dropdown(
                                            id='gallery-folder-dropdown',
                                            options=[
                                                {'label': f or '(root)', 'value': f}
                                                for f in list_s3_folders(
                                                    s3_client, 'dashlab-bucket'
                                                )
                                            ],
                                            value='',  # default root
                                            clearable=False,
                                        ),
                                    ],
                                    style={
                                        'width': '200px',
                                        'display': 'inline-block',
                                        'marginRight': '20px',
                                    },
                                ),
                                html.Div(
                                    [
                                        html.Label('Select File Type:'),
                                        dcc.Dropdown(
                                            id='type-dropdown',
                                            options=[
                                                {'label': 'Images', 'value': 'image'},
                                                {'label': 'PDFs', 'value': 'pdf'},
                                                {'label': 'Audio', 'value': 'audio'},
                                                {'label': 'Text', 'value': 'text'},
                                            ],
                                            value='image',
                                            clearable=False,
                                        ),
                                    ],
                                    style={'width': '200px', 'display': 'inline-block'},
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
    folders = list_s3_folders(s3_client, gallery_bucket)
    options = [{'label': f or '(root)', 'value': f} for f in folders]
    return options


@callback(
    Output('bucket-gallery-container', 'children'),
    Output('delete-status', 'children'),
    Input({'type': 'delete-file-btn', 'file_key': ALL}, 'n_clicks'),
    Input('gallery-folder-dropdown', 'value'),
    Input('type-dropdown', 'value'),
    Input('gallery-bucket-selector', 'value'),
    prevent_initial_call=True,
)
def update_gallery_on_delete(
    n_clicks_list, selected_folder, selected_type, bucket_name
):
    triggered = ctx.triggered_id

    # Make sure it is a dict before accessing 'type'
    if isinstance(triggered, dict) and triggered.get('type') == 'delete-file-btn':
        file_key = triggered['file_key']
        delete_file_from_s3(s3_client, bucket_name, file_key)
        status_msg = f'Deleted {file_key}'
    else:
        status_msg = ''

    # Always refresh gallery
    all_files = list_all_files(s3_client, bucket_name, selected_folder)
    filtered_files = filter_files_by_type(all_files, selected_type)
    gallery_div = build_gallery_layout(s3_client, bucket_name, filtered_files)

    return gallery_div, status_msg
