"""
This module is used to manage files in a consistent manner across the various front-end pages.

Features:
- Connect to S3_bucket and list instances in the bucket for dropdown menus
- Save or delete files on the buckets
- Prepare display of files from s3 to dash, automatically rendering according to the file format.

Dependencies:
- Dash for the html outputs
- Pymongo for the database handling

Configuration:
- All sensitive keys and URLs are loaded from the `config.settings` module

Usage:
Import from pages to quickly set up working UI for various projects, with display and management of files.
"""

import base64
import logging
import mimetypes
from datetime import datetime
from typing import List, Optional, Union

from botocore.exceptions import BotoCoreError, ClientError
from dash import html
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)
AWS_REGION = 'us-east-1'

MONGO_URI = (
    f'mongodb://{settings.mongo_initdb_root_username}:'
    f'{settings.mongo_initdb_root_password}@mongo_db:27017/'
    f'{settings.mongo_initdb_database}?authSource=admin'
)


def list_s3_folders(s3_client, bucket_name) -> List[str]:
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


def list_files_in_s3(
    s3_client, bucket_name: str, folder_name: Optional[str] = None
) -> List[dict]:
    """
    Return a list of dicts suitable for dcc.Dropdown options for files in S3.

    :param bucket_name: Name of the S3 bucket
    :param folder_name: Optional folder prefix
    :return: List of dicts [{"label": ..., "value": ...}]
    """
    if not bucket_name:
        return []

    prefix = f"{folder_name.strip().rstrip('/')}/" if folder_name else ''
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        files = response.get('Contents', [])
        file_keys = [obj['Key'] for obj in files if not obj['Key'].endswith('/')]
        return [{'label': key[len(prefix) :], 'value': key} for key in file_keys]
    except Exception as e:
        logger.error(
            f"Error listing files in bucket '{bucket_name}', folder '{folder_name}': {e}"
        )
        return []


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


def save_file(
    s3_client,
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


def generate_presigned_url(
    s3_client, bucket_name: str, object_key: str, expiration: int = 3600
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


def render_file_preview(
    s3_client, bucket_name: str, file_key: str
) -> tuple[html.Div, str, Optional[str], str]:
    """
    Returns the display component, tags, folder name, and default new-folder value
    for a selected file in S3.

    :param bucket_name: S3 bucket name
    :param file_key: Key of the file in S3
    :return: tuple(display_component, tags_str, folder_name, new_folder_default)
    """
    file_url = generate_presigned_url(s3_client, bucket_name, file_key)
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
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            text = response['Body'].read().decode('utf-8')
            main_component = html.Pre(text, style={'whiteSpace': 'pre-wrap'})
        except Exception as e:
            logger.error(f'Error reading text file {file_key}: {e}')
            main_component = html.Div('Could not read file contents.')
    else:
        main_component = html.Div('Preview not available.')

    # Fetch tags and folder from database
    collection = get_collection()
    metadata = (
        collection.find_one({'file_path': {'$regex': f'{file_key}$'}})
        if collection
        else None
    )

    tags = ', '.join(metadata.get('tags', [])) if metadata else ''

    # Use folder from metadata if available, otherwise fallback to key-derived folder
    folder_name = (
        metadata.get('folder')
        if metadata and 'folder' in metadata
        else ('/'.join(file_key.split('/')[:-1]) if '/' in file_key else '')
    )

    # Add a download link
    download_link = html.A(
        '⬇ Download file',
        href=file_url,
        target='_blank',
        style={'display': 'block', 'marginTop': '10px'},
    )

    display_component = html.Div([main_component, download_link])

    return display_component, tags, folder_name or None, ''


def move_file_and_update_metadata(
    s3_client,
    bucket_name: str,
    file_key: str,
    new_tags: Optional[str] = None,
    target_folder: Optional[str] = None,
) -> str:
    """
    Move a file to a new folder in S3 (if needed) and update its metadata (tags, path) in MongoDB.

    :param bucket_name: Name of the S3 bucket
    :param file_key: Current S3 key of the file
    :param new_tags: New tags as comma-separated string
    :param target_folder: New folder name (optional)
    :return: Status message
    """
    if not file_key:
        return 'No file selected to update.'

    collection = get_collection()
    if collection is None:
        return 'Database connection not available.'

    # Prepare tags list
    tags_list = (
        [tag.strip() for tag in new_tags.split(',') if tag.strip()] if new_tags else []
    )

    # Determine new folder path
    folder_path = target_folder.strip() if target_folder else ''
    filename = file_key.split('/')[-1]

    # Move file if folder changed
    current_folder = '/'.join(file_key.split('/')[:-1])
    if folder_path and folder_path != current_folder:
        new_key = f"{folder_path.rstrip('/')}/{filename}"
        try:
            s3_client.copy_object(
                Bucket=bucket_name,
                CopySource={'Bucket': bucket_name, 'Key': file_key},
                Key=new_key,
            )
            s3_client.delete_object(Bucket=bucket_name, Key=file_key)
            logger.info(f'Moved file from {file_key} to {new_key}')
        except Exception as e:
            logger.error(f'Error moving file in S3: {e}')
            return f'Error moving file: {e}'
    else:
        new_key = file_key

    # Update MongoDB entry
    old_file_url = generate_s3_url(bucket_name, file_key, AWS_REGION)
    new_file_url = generate_s3_url(bucket_name, new_key, AWS_REGION)

    update_result = collection.update_one(
        {'file_path': old_file_url},
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


def delete_file_from_s3(s3_client, bucket_name, filename: str) -> None:
    """
    Delete a file from S3.

    :param filename: Object key (path + filename) in S3
    """
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=filename)
        logger.info(f'Deleted {filename} from S3.')
    except Exception as e:
        logger.error(f'Error deleting {filename} from S3: {e}')


def delete_entries_by_path(s3_client, bucket_name, paths_to_delete: List[str]) -> None:
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
            delete_file_from_s3(s3_client, bucket_name, filename)
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


def upload_files_to_s3(
    s3_client,
    bucket_name: str,
    file_contents: List[str],
    filenames: List[str],
    folder_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> tuple[str, str, List[str]]:
    """
    Upload files to S3 and store metadata in MongoDB.

    :param s3_client: boto3 S3 client
    :param bucket_name: S3 bucket name
    :param file_contents: List of base64-encoded file contents
    :param filenames: List of file names
    :param folder_name: Optional folder to upload into
    :param tags: Optional list of tags
    :return: Tuple of (status_msg, tags_msg, uploaded filenames)
    """
    uploaded_filenames = []
    tags = tags or []

    for content, filename in zip(file_contents, filenames):
        try:
            content_type, content_string = content.split(',')
            decoded = base64.b64decode(content_string)
            file_url = save_file(s3_client, bucket_name, decoded, filename, folder_name)
            store_file_metadata(file_url, tags)
            uploaded_filenames.append(filename)
            logger.info(f"Uploaded {filename} to folder {folder_name or '(root)'}")
        except Exception as e:
            logger.error(f'Error uploading file {filename}: {e}')
            return (
                f'Error uploading {filename}: {e}',
                '',
                uploaded_filenames,
            )

    status_msg = f'Successfully uploaded {len(uploaded_filenames)} file(s).'
    tags_msg = f"Tags applied: {', '.join(tags)}" if tags else 'No tags applied.'
    return status_msg, tags_msg, uploaded_filenames


def handle_deletion(
    s3_client, bucket_name: str, delete_paths: Optional[str]
) -> Optional[str]:
    """
    Delete files from S3 and MongoDB based on comma-separated paths.

    :param bucket_name: S3 bucket name
    :param delete_paths: Comma-separated file paths
    :return: Error message if deletion fails, else None
    """
    if not delete_paths:
        return 'Please enter file paths to delete.'

    paths_to_delete = [p.strip() for p in delete_paths.split(',') if p.strip()]
    if not paths_to_delete:
        return 'No valid paths provided for deletion.'

    delete_entries_by_path(s3_client, bucket_name, paths_to_delete)
    logger.info(f'Deleted entries for paths: {paths_to_delete}')
    return None


def build_database_table(files: list[dict]) -> Union[html.Table, html.Div]:
    """
    Build an HTML table to display database file entries.

    :param files: List of file metadata dicts
    :return: Dash HTML Table or message div if empty
    """
    if not files:
        return html.Div('No file entries found in database.')

    columns = list(files[0].keys())
    table_header = [html.Th(col) for col in columns]

    table_rows = []
    for file in files:
        row = [html.Td(file.get(col, '')) for col in columns]
        table_rows.append(html.Tr(row))

    return html.Table(
        [html.Thead(html.Tr(table_header)), html.Tbody(table_rows)],
        style={'border': '1px solid black', 'borderCollapse': 'collapse'},
    )
