import base64
import logging
import mimetypes
from datetime import datetime
from typing import List, Optional, Union

import boto3
import dash
from botocore.exceptions import BotoCoreError, ClientError
from dash import callback, callback_context, dcc, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from flask import session
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

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


MONGO_URI = (
    f'mongodb://{settings.mongo_initdb_root_username}:'
    f'{settings.mongo_initdb_root_password}@mongo_db:27017/'
    f'{settings.mongo_initdb_database}?authSource=admin'
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


def generate_s3_url(bucket: str, key: str, region: str) -> str:
    """
    Generate the public S3 URL for an object.

    :param bucket: S3 bucket name
    :param key: Object key (path + filename)
    :param region: AWS region of the bucket
    :return: Public URL string
    """
    if region == 'us-east-1':
        return f'https://{bucket}.s3.amazonaws.com/{key}'
    else:
        return f'https://{bucket}.s3.{region}.amazonaws.com/{key}'


########################### Functions ##############################


def generate_presigned_url(
    bucket_name: str, object_key: str, expiration: int = 3600
) -> Optional[str]:
    """
    Generate a pre-signed URL to access a file in S3.

    Parameters:
        bucket_name (str): Name of the S3 bucket.
        object_key (str): Key (path) of the file within the bucket.
        expiration (int): Time in seconds for the URL to remain valid. Default is 3600 (1 hour).

    Returns:
        Optional[str]: A pre-signed URL if successful, or None if generation fails.
    """
    try:
        # Guess MIME type from file extension
        mime_type, _ = mimetypes.guess_type(object_key)

        # Build request parameters
        params = {
            'Bucket': bucket_name,
            'Key': object_key,
        }

        # If MIME type is known and displayable, set headers to inline
        if mime_type:
            params['ResponseContentDisposition'] = 'inline'
            params['ResponseContentType'] = mime_type
        else:
            # Default to download if MIME type is unknown
            params['ResponseContentDisposition'] = 'attachment'

        # Generate the pre-signed URL
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object', Params=params, ExpiresIn=expiration
        )

        logger.info(f'Generated pre-signed URL for: s3://{bucket_name}/{object_key}')
        return url

    except (BotoCoreError, ClientError) as e:
        logger.error(f'Error generating pre-signed URL for {object_key}: {e}')
        return None


def get_collection():
    """
    Get MongoDB collection for file metadata.

    :return: pymongo Collection object or None if connection fails
    """
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')  # Test connection
        db = client.get_database()
        return db['file_metadata']
    except ServerSelectionTimeoutError:
        logger.info('Warning: Could not connect to MongoDB.')
        return None


def list_s3_folders(bucket_name) -> List[str]:
    """
    List top-level folders in the S3 bucket.

    :return: List of folder names (strings), including empty string for root
    """
    if not bucket_name:
        logger.warning('No bucket name provided to list_s3_folders')
        return []
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        prefixes = response.get('CommonPrefixes', [])
        folders = [p['Prefix'].rstrip('/') for p in prefixes]
        return [''] + folders  # Include root folder as empty string
    except Exception as e:
        logger.error(f'Failed to list S3 folders: {e}')
        return []


def save_file(
    bucket_name,
    decoded_content: bytes,
    filename: str,
    folder_name: Optional[str] = None,
) -> str:
    """
    Save a file to S3 with an optional folder prefix.

    :param decoded_content: File content as bytes
    :param filename: Name of the file
    :param folder_name: Optional folder prefix within the bucket
    :return: Public URL of the saved file
    """
    if folder_name:
        folder_name = folder_name.strip().strip('/')
        key = f'{folder_name}/{filename}'
    else:
        key = filename

    s3_client.put_object(Bucket=bucket_name, Key=key, Body=decoded_content)
    s3_url = generate_s3_url(bucket_name, key, AWS_REGION)
    return s3_url


def store_file_metadata(file_path: str, tags: List[str]) -> None:
    """
    Store file metadata in MongoDB.

    :param file_path: URL or path of the stored file
    :param tags: List of tags associated with the file
    """
    collection = get_collection()
    if collection is None:
        logger.info('Skipping metadata storage: no DB connection.')
        return
    file_entry = {
        'file_path': file_path,
        'tags': tags,
        'timestamp': datetime.utcnow(),
    }
    collection.insert_one(file_entry)


def delete_file_from_s3(bucket_name, filename: str) -> None:
    """
    Delete a file from S3.

    :param filename: Object key (path + filename) in S3
    """
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=filename)
        logger.info(f'Deleted {filename} from S3.')
    except Exception as e:
        logger.error(f'Error deleting {filename} from S3: {e}')


def delete_entries_by_path(bucket_name, paths_to_delete: List[str]) -> None:
    """
    Delete files from S3 and remove their metadata from MongoDB.

    :param paths_to_delete: List of file paths (URLs) to delete
    """
    collection = get_collection()
    if collection is None:
        logger.info('Skipping deletion: no DB connection.')
        return

    for file_path in paths_to_delete:
        if file_path.startswith('https://'):
            # Extract S3 key from URL
            parts = file_path.split('/')
            filename = '/'.join(parts[3:])  # bucket + region parts removed
            delete_file_from_s3(bucket_name, filename)
        else:
            logger.warning(f'Invalid file path for deletion: {file_path}')

    collection.delete_many({'file_path': {'$in': paths_to_delete}})


def fetch_all_files() -> List[dict]:
    """
    Fetch all file metadata entries from MongoDB.

    :return: List of file metadata dicts
    """
    collection = get_collection()
    if collection is None:
        logger.info('Skipping fetch: no DB connection.')
        return []
    return list(collection.find({}, {'_id': 0}))


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
def upload_files(
    file_contents: Optional[List[str]],
    filenames: Optional[List[str]],
    selected_folder: Optional[str],
    new_folder_name: Optional[str],
    file_tags: Optional[str],
    bucket_name: str,
) -> tuple[str, str, html.Ul]:
    """
    Upload files to S3 bucket, optionally into a folder.
    Store metadata (file URL and tags) into MongoDB.
    Display upload and tags status and list of uploaded files.

    :param file_contents: List of base64 encoded file contents
    :param filenames: List of filenames
    :param selected_folder: Folder selected from dropdown (optional)
    :param new_folder_name: New folder name entered by user (optional)
    :param file_tags: Tags entered as comma-separated string (optional)
    :return: Tuple of upload status message, tags status, and uploaded files list element
    """
    if not file_contents or not filenames:
        raise PreventUpdate

    folder_name = new_folder_name.strip() if new_folder_name else selected_folder

    tags_list = []
    if file_tags:
        tags_list = [tag.strip() for tag in file_tags.split(',') if tag.strip()]

    uploaded_filenames = []

    for content, filename in zip(file_contents, filenames):
        try:
            content_type, content_string = content.split(',')
            decoded = base64.b64decode(content_string)
            file_url = save_file(bucket_name, decoded, filename, folder_name)
            store_file_metadata(file_url, tags_list)
            uploaded_filenames.append(filename)
            logger.info(f"Uploaded {filename} to folder {folder_name or '(root)'}")
        except Exception as e:
            logger.error(f'Error uploading file {filename}: {e}')
            return (
                f'Error uploading {filename}: {e}',
                '',
                html.Ul([html.Li(filename) for filename in uploaded_filenames]),
            )

    status_msg = f'Successfully uploaded {len(uploaded_filenames)} file(s).'
    tags_msg = (
        f"Tags applied: {', '.join(tags_list)}" if tags_list else 'No tags applied.'
    )
    return status_msg, tags_msg, html.Ul([html.Li(f) for f in uploaded_filenames])


@callback(
    Output('database-entries-list', 'children'),
    Input('refresh-btn', 'n_clicks'),
    Input('delete-btn', 'n_clicks'),
    State('delete-paths-input', 'value'),
    State('bucket-selector', 'value'),
    prevent_initial_call=True,
)
def update_database_entries(
    refresh_clicks: int,
    delete_clicks: int,
    delete_paths: Optional[str],
    bucket_name: str,
) -> Union[html.Table, html.Div]:
    """
    Update the displayed database entries table.
    Handles both refresh requests and deletions.
    Deletes files from S3 and entries from MongoDB if delete button clicked.

    :param refresh_clicks: Number of clicks on refresh button
    :param delete_clicks: Number of clicks on delete button
    :param delete_paths: Comma-separated string of file paths to delete
    :return: HTML Table with database entries or a message div
    """
    triggered_id = callback_context.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'delete-btn':
        if not delete_paths:
            return html.Div('Please enter file paths to delete.')
        paths_to_delete = [p.strip() for p in delete_paths.split(',') if p.strip()]
        if not paths_to_delete:
            return html.Div('No valid paths provided for deletion.')
        delete_entries_by_path(bucket_name, paths_to_delete)
        logger.info(f'Deleted entries for paths: {paths_to_delete}')

    files = fetch_all_files()

    if not files:
        return html.Div('No file entries found in database.')

    # Build table headers dynamically from keys of first entry
    columns = list(files[0].keys())
    table_header = [html.Th(col) for col in columns]

    # Build table rows
    table_rows = []
    for file in files:
        row = [html.Td(file.get(col, '')) for col in columns]
        table_rows.append(html.Tr(row))

    return html.Table(
        [html.Thead(html.Tr(table_header)), html.Tbody(table_rows)],
        style={'border': '1px solid black', 'borderCollapse': 'collapse'},
    )


@callback(
    Output('file-selector', 'options'),
    Input('folder-selector', 'value'),
    Input('bucket-selector', 'value'),
)
def update_file_selector_options(
    folder_name: Optional[str], bucket_name: str
) -> List[dict]:
    """
    Update the file dropdown options based on the selected folder.

    :param folder_name: Selected folder name or empty string for root
    :return: List of options dicts for dcc.Dropdown
    """

    if not bucket_name:
        return []

    prefix = f'{folder_name.strip()}/' if folder_name else ''
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        files = response.get('Contents', [])
        file_keys = [obj['Key'] for obj in files if not obj['Key'].endswith('/')]
        options = [{'label': key[len(prefix) :], 'value': key} for key in file_keys]
        return options
    except Exception as e:
        logger.error(f"Error listing files in folder '{folder_name}': {e}")
        return []


def is_image(file_key: str) -> bool:
    return file_key.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))


def is_pdf(file_key: str) -> bool:
    return file_key.lower().endswith('.pdf')


def is_audio(file_key: str) -> bool:
    return file_key.lower().endswith(('.mp3', '.wav', '.ogg', 'm4a'))


def is_raw_text(file_key: str) -> bool:
    return file_key.lower().endswith(
        ('.txt', '.md', '.log', '.csv', '.json', '.xml', '.yaml', '.yml')
    )


@callback(
    Output('file-display', 'children'),
    Output('edit-tags', 'value'),
    Output('edit-folder-dropdown', 'value'),
    Output('edit-new-folder', 'value'),
    Input('file-selector', 'value'),
    State('bucket-selector', 'value'),
)
def display_selected_file(
    file_key: Optional[str],
    bucket_name: str,
) -> tuple[html.Div, str, Optional[str], str]:
    if not file_key:
        return html.Div('No file selected.'), '', None, ''

    file_url = generate_presigned_url(bucket_name, file_key)

    logging.info(f'Generated url: {file_url}')

    # Determine file type and render appropriately
    if is_image(file_key):
        main_component = html.Img(src=file_url, style={'maxWidth': '100%'})
    elif is_pdf(file_key):
        main_component = html.Iframe(
            src=file_url, style={'width': '100%', 'height': '600px'}
        )
    elif is_audio(file_key):
        main_component = html.Audio(src=file_url, controls=True)

    elif is_raw_text(file_key):
        # Download file content using presigned URL or S3 client
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            text = response['Body'].read().decode('utf-8')
            main_component = html.Pre(text, style={'whiteSpace': 'pre-wrap'})
        except Exception as e:
            logger.error(f'Error reading text file {file_key}: {e}')
            main_component = html.Div('Could not read file contents.')
    else:
        main_component = html.Div('Preview not available.')

    # Fetch tags from database
    collection = get_collection()
    metadata = collection.find_one({'file_path': {'$regex': f'{file_key}$'}})
    tags = ', '.join(metadata.get('tags', [])) if metadata else ''

    folder_name = '/'.join(file_key.split('/')[:-1]) if '/' in file_key else ''
    # Always add a download link
    download_link = html.A(
        '⬇ Download file',
        href=file_url,
        target='_blank',
        style={'display': 'block', 'marginTop': '10px'},
    )

    display_component = html.Div([main_component, download_link])

    return display_component, tags, folder_name or None, ''


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
def update_file_metadata(
    n_clicks: int,
    selected_file_key: Optional[str],
    new_tags: Optional[str],
    selected_folder: Optional[str],
    new_folder_name: Optional[str],
    bucket_name: str,
) -> str:
    """
    Update file tags and optionally move the file to a new folder.

    :param n_clicks: Number of update button clicks
    :param selected_file_key: Currently selected file S3 key
    :param new_tags: New tags as comma-separated string
    :param selected_folder: Selected folder from dropdown for new location
    :param new_folder_name: New folder name input (optional)
    :return: Status message string
    """
    if not selected_file_key:
        return 'No file selected to update.'

    collection = get_collection()
    if collection is None:
        return 'Database connection not available.'

    # Prepare tags list
    tags_list = []
    if new_tags:
        tags_list = [tag.strip() for tag in new_tags.split(',') if tag.strip()]

    # Determine new folder path
    target_folder = (
        new_folder_name.strip() if new_folder_name else selected_folder or ''
    )

    old_key = selected_file_key
    filename = old_key.split('/')[-1]

    # If folder changed, move file in S3
    if target_folder and target_folder.strip() != '/'.join(old_key.split('/')[:-1]):
        new_key = f"{target_folder.strip().rstrip('/')}/{filename}"
        try:
            # Copy old object to new key
            s3_client.copy_object(
                Bucket=bucket_name,
                CopySource={'Bucket': bucket_name, 'Key': old_key},
                Key=new_key,
            )
            # Delete old object
            s3_client.delete_object(Bucket=bucket_name, Key=old_key)
            logger.info(f'Moved file from {old_key} to {new_key}')
        except Exception as e:
            logger.error(f'Error moving file in S3: {e}')
            return f'Error moving file: {e}'
    else:
        new_key = old_key

    new_file_url = generate_s3_url(bucket_name, new_key, AWS_REGION)

    # Update DB entry
    update_result = collection.update_one(
        {'file_path': generate_s3_url(bucket_name, old_key, AWS_REGION)},
        {
            '$set': {
                'file_path': new_file_url,
                'tags': tags_list,
                'timestamp': datetime.utcnow(),
            }
        },
    )

    if update_result.matched_count == 0:
        return 'File metadata not found in database.'

    return 'File metadata and location updated successfully.'


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
    edit_folders = list_s3_folders(edit_bucket)
    upload_folders = list_s3_folders(upload_bucket)
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
