import logging
from typing import List, Optional, Union

import boto3
import dash
from dash import callback, callback_context, dcc, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from flask import session

from app.services.utils.file_utils import (
    build_database_table,
    fetch_all_files,
    handle_deletion,
    list_files_in_s3,
    list_s3_folders,
    move_file_and_update_metadata,
    render_file_preview,
    upload_files_to_s3,
)
from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)

if settings.env != 'testing':
    dash.register_page(
        __name__,
        path='/file-explorer',
        name='S3 File Explorer',
        order=1,
    )


# AWS S3 Configuration
AWS_REGION = 'us-east-1'

# Initialize boto3 S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=AWS_REGION,
)

########################### Functions ##############################


def get_user_allowed_buckets():
    """Return allowed buckets from the current user session."""
    if 'ALLOWED_BUCKETS' in session:
        return session['ALLOWED_BUCKETS']
    # fallback
    return {'splitbox-bucket': 'us-east-1'}


def bucket_dropdown(layout_id: str):
    """Create a dropdown component for buckets."""
    # Do NOT access session here at import time.
    # Return a function that will be called when rendering the layout.
    return html.Div(
        id=layout_id,
        children=[
            dcc.Dropdown(
                id=layout_id,
                # Use callback to populate options dynamically
                options=[],
                value=None,
                clearable=False,
                style={'width': '300px'},
            )
        ],
    )


# Page layout definition
layout = html.Div(
    [
        dcc.Tabs(
            [
                dcc.Tab(
                    label='Upload Files',
                    children=[
                        html.H2('Upload Files'),
                        html.Label('Select the S3 bucket you want to use:'),
                        bucket_dropdown(layout_id='upload-bucket-selector'),
                        html.Br(),
                        html.Label('Select an existing folder:'),
                        dcc.Dropdown(
                            id='folder-dropdown',
                            options=[],
                            placeholder='Select a folder (optional)',
                            clearable=True,
                            style={'width': '300px'},
                        ),
                        html.Br(),
                        html.Label('Or Create a new one:'),
                        html.Br(),
                        dcc.Input(
                            id='new-folder-name',
                            type='text',
                            placeholder='Enter new folder name (optional)',
                            style={'width': '300px'},
                        ),
                        html.Br(),
                        html.Br(),
                        html.Label('You also can add tags to your file:'),
                        html.Br(),
                        dcc.Input(
                            id='file-tags',
                            type='text',
                            placeholder='Enter tags (comma-separated)',
                            style={'width': '400px'},
                        ),
                        html.Br(),
                        html.Br(),
                        dcc.Upload(
                            id='upload-files',
                            children=html.Button('Upload File', id='upload-button'),
                            multiple=True,
                        ),
                        html.Br(),
                        html.Div(id='upload-status'),
                        html.Div(id='tags-status'),
                        html.Div(id='uploaded-files-list'),
                        html.Br(),
                        html.Br(),
                    ],
                ),
                dcc.Tab(
                    label='View & Edit Files',
                    children=[
                        html.H2('Select and Edit Existing Files'),
                        html.Label('Select a Bucket here:'),
                        bucket_dropdown(layout_id='bucket-selector'),
                        html.Label('Select a Folder:'),
                        dcc.Dropdown(
                            id='folder-selector',
                            options=[],
                            placeholder='Select a folder',
                            clearable=True,
                            style={'width': '300px'},
                        ),
                        html.Br(),
                        html.Label('Select a File:'),
                        dcc.Dropdown(
                            id='file-selector',
                            placeholder='Select a file',
                            style={'width': '600px'},
                            clearable=True,
                        ),
                        html.Br(),
                        html.Div(id='file-display'),
                        html.Br(),
                        html.Label('Edit Tags (comma-separated):'),
                        dcc.Input(
                            id='edit-tags', type='text', style={'width': '600px'}
                        ),
                        html.Br(),
                        html.Br(),
                        html.Label('Change Folder:'),
                        dcc.Dropdown(
                            id='edit-folder-dropdown',
                            options=[],
                            placeholder='Select folder',
                            clearable=True,
                            style={'width': '300px'},
                        ),
                        html.Br(),
                        html.Label('Or create new folder:'),
                        dcc.Input(
                            id='edit-new-folder',
                            type='text',
                            placeholder='Enter new folder name',
                            style={'width': '300px'},
                        ),
                        html.Br(),
                        html.Br(),
                        html.Button(
                            'Update File Metadata & Location', id='update-file-btn'
                        ),
                        html.Div(id='update-status'),
                    ],
                ),
                dcc.Tab(
                    label='Database entries',
                    children=[
                        html.H3('Database Entries'),
                        html.Div(id='database-entries-list'),
                        html.Label('Enter file paths to Delete (comma-separated):'),
                        html.Br(),
                        html.Br(),
                        dcc.Input(
                            id='delete-paths-input',
                            type='text',
                            placeholder='Enter file paths to delete',
                        ),
                        html.Br(),
                        html.Br(),
                        html.Button(
                            'Delete Selected Entries', id='delete-btn', n_clicks=0
                        ),
                        html.Br(),
                        html.Br(),
                        html.Button('Refresh Table', id='refresh-btn', n_clicks=0),
                        html.Hr(),
                    ],
                ),
            ]
        )
    ]
)


########################### Callbacks ##############################


@callback(
    Output('upload-status', 'children'),
    Output('tags-status', 'children'),
    Output('uploaded-files-list', 'children'),
    Input('upload-files', 'contents'),
    State('upload-files', 'filename'),
    State('folder-dropdown', 'value'),
    State('new-folder-name', 'value'),
    State('file-tags', 'value'),
    State('bucket-selector', 'value'),
)
def upload_files_callback(
    file_contents: Optional[List[str]],
    filenames: Optional[List[str]],
    selected_folder: Optional[str],
    new_folder_name: Optional[str],
    file_tags: Optional[str],
    bucket_name: str,
) -> tuple[str, str, html.Ul]:
    if not file_contents or not filenames:
        raise PreventUpdate

    folder_name = new_folder_name.strip() if new_folder_name else selected_folder
    tags_list = (
        [tag.strip() for tag in file_tags.split(',') if tag.strip()]
        if file_tags
        else []
    )

    status_msg, tags_msg, uploaded_files = upload_files_to_s3(
        s3_client, bucket_name, file_contents, filenames, folder_name, tags_list
    )

    return status_msg, tags_msg, html.Ul([html.Li(f) for f in uploaded_files])


@callback(
    Output('database-entries-list', 'children'),
    Input('refresh-btn', 'n_clicks'),
    Input('delete-btn', 'n_clicks'),
    State('delete-paths-input', 'value'),
    State('bucket-selector', 'value'),
    prevent_initial_call=True,
)
def update_database_entries_callback(
    refresh_clicks: int,
    delete_clicks: int,
    delete_paths: Optional[str],
    bucket_name: str,
) -> Union[html.Table, html.Div]:
    triggered_id = callback_context.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'delete-btn':
        error_msg = handle_deletion(s3_client, bucket_name, delete_paths)
        if error_msg:
            return html.Div(error_msg)

    files = fetch_all_files()
    return build_database_table(files)


@callback(
    Output('file-selector', 'options'),
    Input('folder-selector', 'value'),
    Input('bucket-selector', 'value'),
)
def update_file_selector_options(folder_name: Optional[str], bucket_name: str):
    return list_files_in_s3(s3_client, bucket_name, folder_name)


@callback(
    Output('file-display', 'children'),
    Output('edit-tags', 'value'),
    Output('edit-folder-dropdown', 'value'),
    Output('edit-new-folder', 'value'),
    Input('file-selector', 'value'),
    State('bucket-selector', 'value'),
)
def display_selected_file(file_key: Optional[str], bucket_name: str):
    if not file_key:
        return html.Div('No file selected.'), '', None, ''
    return render_file_preview(s3_client, bucket_name, file_key)


@callback(
    Output('update-status', 'children'),
    Input('update-file-btn', 'n_clicks'),
    State('file-selector', 'value'),
    State('edit-tags', 'value'),
    State('edit-folder-dropdown', 'value'),
    State('edit-new-folder', 'value'),
    State('bucket-selector', 'value'),
    prevent_initial_call=True,
)
def update_file_metadata_callback(
    n_clicks: int,
    selected_file_key: Optional[str],
    new_tags: Optional[str],
    selected_folder: Optional[str],
    new_folder_name: Optional[str],
    bucket_name: str,
) -> str:
    target_folder = new_folder_name or selected_folder
    return move_file_and_update_metadata(
        s3_client, bucket_name, selected_file_key, new_tags, target_folder
    )


@callback(
    Output('folder-dropdown', 'options'),
    Output('folder-selector', 'options'),
    Output('edit-folder-dropdown', 'options'),
    Input('upload-files', 'contents'),
    Input('upload-button', 'n_clicks'),
    Input('bucket-selector', 'value'),
    Input('upload-bucket-selector', 'value'),
)
def refresh_folder_options(
    upload_contents, update_clicks, edit_bucket: str, upload_bucket
):
    edit_folders = list_s3_folders(s3_client, edit_bucket)
    upload_folders = list_s3_folders(s3_client, upload_bucket)
    options_edit = [{'label': f or '(root)', 'value': f} for f in edit_folders]
    options_upload = [{'label': f or '(root)', 'value': f} for f in upload_folders]
    return options_upload, options_edit, options_edit


@callback(
    Output('upload-bucket-selector', 'options'),
    Output('upload-bucket-selector', 'value'),
    Input('url', 'pathname'),  # Trigger when page is loaded
)
def populate_upload_bucket_dropdown(pathname):
    """Populate bucket dropdown dynamically based on user session."""
    if 'user' not in session:
        raise PreventUpdate
    buckets = session.get('ALLOWED_BUCKETS', {'splitbox-bucket': 'us-east-1'})
    default = session.get('DEFAULT_BUCKET', list(buckets.keys())[0])
    options = [{'label': b, 'value': b} for b in buckets.keys()]
    return options, default


@callback(
    Output('bucket-selector', 'options'),
    Output('bucket-selector', 'value'),
    Input('url', 'pathname'),  # Trigger when page is loaded
)
def populate_bucket_dropdown(pathname):
    """Populate bucket dropdown dynamically based on user session."""
    if 'user' not in session:
        raise PreventUpdate
    buckets = session.get('ALLOWED_BUCKETS', {'splitbox-bucket': 'us-east-1'})
    default = session.get('DEFAULT_BUCKET', list(buckets.keys())[0])
    options = [{'label': b, 'value': b} for b in buckets.keys()]
    return options, default
