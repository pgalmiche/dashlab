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
import io
import json
import logging
import mimetypes
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional, Union

import boto3
import plotly.graph_objects as go
import requests
from botocore.exceptions import BotoCoreError, ClientError
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from dash import dcc, html
from PIL import ExifTags, Image
from PIL.ExifTags import GPSTAGS, TAGS
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from config.logging import setup_logging
from config.settings import settings

# 🔑 In-memory cache: stores final images_with_gps list per (bucket, sorted_keys)
#    - maxsize: number of distinct key sets to remember
#    - ttl: seconds to keep (e.g., 600 = 10 minutes)
_gps_mem_cache = TTLCache(maxsize=128, ttl=600)
thumbnail_exists_cache = TTLCache(maxsize=2048, ttl=300)  # 5 min cache

# --- Simple in-memory cache ---
_presigned_cache: dict[str, tuple[str, float]] = {}  # {cache_key: (url, expiry_time)}
_PRESIGNED_TTL = 900  # 15 min internal refresh window (can be < expiration)

# Cache up to 512 distinct calls for 5 minutes (adjust as needed)
_s3_cache = TTLCache(maxsize=512, ttl=300)


setup_logging()
logger = logging.getLogger(__name__)

logging.getLogger('PIL').setLevel(logging.WARNING)
AWS_REGION = 'us-east-1'

MONGO_URI = (
    f'mongodb://{settings.mongo_initdb_root_username}:'
    f'{settings.mongo_initdb_root_password}@mongo_db:27017/'
    f'{settings.mongo_initdb_database}?authSource=admin'
)

BUCKET_REGIONS_MAP = {
    'splitbox-bucket': 'us-east-1',
    'personnal-files-pg': 'us-east-1',
    'dashlab-bucket': 'us-east-1',
    'galmiche-family': 'eu-west-3',
    'pgvv': 'eu-west-3',
    'splitbox-contributor': 'eu-west-3',
}


@lru_cache(maxsize=32)
def get_s3_client(bucket_name: str):
    region = BUCKET_REGIONS_MAP.get(bucket_name, 'us-east-1')
    return boto3.client(
        's3',
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=region,
    )


def get_current_username(session) -> Optional[str]:
    user = session.get('user')
    if not user:
        return None
    return user.get('cognito:username') or user.get('username') or user.get('email')


def get_allowed_folders_for_user(session, s3_client, bucket_name):
    """
    Return all folders the user is allowed to see, including subfolders:
    - shared/ and all its subfolders
    - username/inputs, username/outputs and all their subfolders
    """
    username = get_current_username(session)
    existing = list_s3_folders(s3_client, bucket_name)  # all folder prefixes

    allowed = []

    # Shared and all its subfolders
    shared_folders = [f for f in existing if f.startswith('shared/')]
    if 'shared/' not in shared_folders:
        allowed.append('shared/')
    allowed.extend(shared_folders)

    # User namespace and all its subfolders
    user_prefix = f'{username}/inputs/'
    user_folders = [f for f in existing if f.startswith(user_prefix)]

    # Ensure default input/output
    for default in [f'{username}/inputs/', f'{username}/outputs/']:
        if default not in user_folders:
            user_folders.append(default)

    allowed.extend(user_folders)

    # Remove duplicates and sort
    return sorted(list(set(allowed)))


def list_files_in_s3(
    s3_client,
    bucket_name: str,
    folder_name: Optional[str] = None,
    recursive: bool = False,
) -> List[dict]:
    """Return list of dicts suitable for dcc.Dropdown options.

    If recursive=True, include files in subfolders.
    """
    if not bucket_name:
        return []

    try:
        keys = _cached_list_files_in_s3(s3_client, bucket_name, folder_name)
        prefix = f"{folder_name.strip().rstrip('/')}/" if folder_name else ''

        files = []
        for key in keys:
            if recursive:
                # Keep the full relative path after the prefix
                label = key[len(prefix) :]
                files.append({'label': label, 'value': key})
            else:
                # Only top-level files: no "/" after prefix
                rest = key[len(prefix) :]
                if '/' not in rest:
                    files.append({'label': rest, 'value': key})

        return files
    except Exception as e:
        logger.error(
            f"Error listing files in bucket '{bucket_name}', folder '{folder_name}': {e}"
        )
        return []


def list_all_files(
    s3_client, bucket_name: str, folder_name: Optional[str] = None
) -> List[str]:
    """Return all file keys in a bucket or a specific folder."""
    try:
        return _cached_list_files_in_s3(s3_client, bucket_name, folder_name)
    except Exception as e:
        logger.error(f'Failed to list all files: {e}')
        return []


def list_s3_folders(s3_client, bucket_name) -> List[str]:
    """List top-level folders in the S3 bucket (includes root)."""
    if not bucket_name:
        logger.warning('No bucket name provided to list_s3_folders')
        return []
    try:
        folders = _cached_list_s3_folders(s3_client, bucket_name)
        return [''] + folders
    except Exception as e:
        logger.error(f'Failed to list S3 folders: {e}')
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
    return file_key.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a', '.webm'))


def is_video(file_key: str) -> bool:
    return file_key.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv'))


def is_raw_text(file_key: str) -> bool:
    return file_key.lower().endswith(
        ('.txt', '.md', '.log', '.csv', '.json', '.xml', '.yaml', '.yml')
    )


def generate_presigned_url(
    s3_client, bucket_name: str, object_key: str, expiration: int = 3600
) -> Optional[str]:
    """
    Generate a cached pre-signed URL to access a file in S3.

    - Uses a 15-minute in-memory cache to avoid regenerating URLs
      on every render.
    - Still respects the `expiration` you pass to S3.

    Parameters
    ----------
    bucket_name : str
        Name of the S3 bucket.
    object_key : str
        Key (path) of the file within the bucket.
    expiration : int
        Time in seconds for the URL to remain valid (default 3600).

    Returns
    -------
    Optional[str]
        A cached or freshly generated pre-signed URL.
    """
    try:
        cache_key = f'{bucket_name}/{object_key}/{expiration}'
        now = time.time()

        # Reuse if still valid in our TTL window
        if cache_key in _presigned_cache:
            url, expiry = _presigned_cache[cache_key]
            if now < expiry:
                return url

        # Guess MIME type from file extension
        mime_type, _ = mimetypes.guess_type(object_key)

        params = {'Bucket': bucket_name, 'Key': object_key}
        if mime_type:
            params['ResponseContentDisposition'] = 'inline'
            params['ResponseContentType'] = mime_type
        else:
            params['ResponseContentDisposition'] = 'attachment'

        # Generate fresh URL
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object', Params=params, ExpiresIn=expiration
        )

        # Cache for a safe window (shorter than S3 expiration)
        _presigned_cache[cache_key] = (url, now + min(_PRESIGNED_TTL, expiration - 60))

        logger.info(
            f'[CacheMiss] Generated pre-signed URL for: s3://{bucket_name}/{object_key}'
        )
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


def render_viz_from_s3_json(file_url: str):
    """
    Fetch JSON from S3 and render as Dash Graphs server-side.
    Returns a list of dcc.Graph components.
    """
    if not file_url:
        return html.Div('No visualization available.')

    try:
        resp = requests.get(file_url)
        resp.raise_for_status()
        data = (
            resp.json()
        )  # {"waveform": "<json string>", "spectrogram": "<json string>"}

        graphs = []
        for name, fig_json in data.items():
            fig_dict = json.loads(fig_json)
            graphs.append(
                dcc.Graph(
                    id=f'graph-{name}',
                    figure=fig_dict,
                    style={'width': '100%', 'height': '400px', 'marginBottom': '20px'},
                )
            )
        return graphs

    except Exception as e:
        return html.Div(f'Error loading visualization: {e}')


@lru_cache(maxsize=2048)  # adjust size as needed
def get_thumbnail_key(file_key: str) -> str:
    """
    Convert an original file key to the corresponding thumbnail key.
    Example: 'folder/image.jpg' -> 'thumbnails/folder/image.jpg'

    Uses an LRU cache to avoid recomputing for the same keys repeatedly.
    """
    return f'thumbnails/{file_key}'


def thumbnail_exists(s3_client, bucket, key):
    if key in thumbnail_exists_cache:
        return True
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        thumbnail_exists_cache[key] = True
        return True
    except s3_client.exceptions.ClientError:
        return False


def move_file_and_update_metadata(
    s3_client,
    bucket_name: str,
    file_key: str,
    new_tags: Optional[str] = None,
    target_folder: Optional[str] = None,
    new_name: Optional[str] = None,
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
    # If renaming → preserve extension
    if new_name:
        _, ext = os.path.splitext(filename)
        filename = f'{new_name}{ext}'

    # Move file if folder changed
    current_folder = '/'.join(file_key.split('/')[:-1])
    if folder_path and folder_path != current_folder or new_name:
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
    """
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=filename)
        logger.info(f'Deleted {filename} from S3.')

        # 🔑 Invalidate folder cache so gallery refreshes instantly
        folder_name = '/'.join(filename.split('/')[:-1]) or None
        invalidate_s3_cache(bucket_name, folder_name)
    except Exception as e:
        logger.error(f'Error deleting {filename} from S3: {e}')


def delete_entries_by_path(s3_client, bucket_name, paths_to_delete: List[str]) -> None:
    """
    Delete files from S3 and remove their metadata from MongoDB.
    """
    collection = get_collection()
    if collection is None:
        logger.info('Skipping deletion: no DB connection.')
        return

    affected_folders = set()

    for file_path in paths_to_delete:
        if file_path.startswith('https://'):
            parts = file_path.split('/')
            filename = '/'.join(parts[3:])  # remove bucket + region
            delete_file_from_s3(s3_client, bucket_name, filename)
            affected_folders.add('/'.join(filename.split('/')[:-1]) or None)
        else:
            logger.warning(f'Invalid file path for deletion: {file_path}')

    # ✅ Invalidate caches for all affected folders
    for folder in affected_folders:
        invalidate_s3_cache(bucket_name, folder)

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
    file_contents: list[str],
    filenames: list[str],
    folder_name: str = '',
    tags: list[str] = None,
    use_presigned: bool = False,
    expires_in: int = 300,  # presigned URL expiry in seconds
):
    """
    Upload files to S3. If use_presigned=True, return presigned POSTs instead of uploading via server.

    :param s3_client: boto3 S3 client
    :param bucket_name: S3 bucket name
    :param file_contents: List of base64-encoded file strings
    :param filenames: List of filenames
    :param folder_name: Optional folder prefix
    :param tags: Optional list of tags
    :param use_presigned: If True, generate presigned POSTs instead of uploading directly
    :param expires_in: Presigned URL expiry (seconds)
    :return: (status_msg, tags_msg, uploaded_filenames or presigned_posts)
    """
    tags = tags or []
    uploaded_files = []

    def _upload_direct(content, filename):
        content_type, content_string = content.split(',')
        file_bytes = io.BytesIO(base64.b64decode(content_string))
        key = f'{folder_name}/{filename}' if folder_name else filename
        s3_client.upload_fileobj(file_bytes, bucket_name, key)
        file_url = f's3://{bucket_name}/{key}'
        store_file_metadata(file_url, tags)
        return filename

    def _generate_presigned(content, filename):
        key = f'{folder_name}/{filename}' if folder_name else filename
        presigned_post = s3_client.generate_presigned_post(
            Bucket=bucket_name,
            Key=key,
            Fields={'Content-Type': 'application/octet-stream'},
            Conditions=[['starts-with', '$Content-Type', '']],
            ExpiresIn=expires_in,
        )
        return {'filename': filename, 'key': key, 'presigned_post': presigned_post}

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for content, filename in zip(file_contents, filenames):
            if use_presigned:
                futures.append(executor.submit(_generate_presigned, content, filename))
            else:
                futures.append(executor.submit(_upload_direct, content, filename))

        for f in futures:
            try:
                uploaded_files.append(f.result())
            except Exception as e:
                logger.error(f'Failed to upload a file: {e}')

    status_msg = f'Processed {len(uploaded_files)} file(s) in {bucket_name} bucket.'
    tags_msg = f"Tags applied: {', '.join(tags)}" if tags else 'No tags applied.'
    return status_msg, tags_msg, uploaded_files


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


def filter_files_by_type(file_keys: List[str], file_type: str) -> List[str]:
    """
    Filter S3 file keys by type: 'image', 'pdf', 'audio', 'text'.

    :param file_keys: List of S3 object keys
    :param file_type: Desired type ("image", "pdf", "audio", "text")
    :return: List of keys matching the type
    """
    type_check = {
        'image': is_image,
        'pdf': is_pdf,
        'audio': is_audio,
        'text': is_raw_text,
        'video': is_video,
    }.get(file_type.lower())

    if not type_check:
        return []

    return [key for key in file_keys if type_check(key)]


def generate_presigned_uploads(s3_client, bucket_name, filenames, folder_name=''):
    presigned_posts = []
    for filename in filenames:
        key = f'{folder_name}/{filename}' if folder_name else filename
        presigned_post = s3_client.generate_presigned_post(
            Bucket=bucket_name,
            Key=key,
            Fields={'Content-Type': 'application/octet-stream'},
            Conditions=[['starts-with', '$Content-Type', '']],
            ExpiresIn=3600,  # 1 hour
        )
        presigned_posts.append(
            {'filename': filename, 'key': key, 'presigned_post': presigned_post}
        )
    return presigned_posts


def get_viz_file_key(file_key: str, username: str = None) -> str:
    """
    Compute the expected S3 key for the Plotly viz JSON.

    Args:
        file_key: full path of the input file relative to S3 bucket, e.g. "Mikasound/billie_chino.mp3"
        username: optional username prefix (if your outputs are under {username}/outputs/...)

    Returns:
        str: S3 key to the _viz.json
    """
    # Extract the file stem
    file_stem, _ = os.path.splitext(os.path.basename(file_key))

    # Get folder path of file_key without filename
    folder_path = os.path.dirname(file_key)  # e.g., "Mikasound" or "inputs/recorded"

    # Build the key with optional username prefix
    prefix = f'{username}/' if username else ''
    viz_key = f'{prefix}outputs/{folder_path}/{os.path.basename(file_key)}/analysis/{file_stem}_viz.json'
    return viz_key


def get_analysis_prefix(file_key: str, username: str) -> str:
    """
    Compute the S3 prefix where analysis (_viz.json) files are stored for a given input file.

    Args:
        file_key: full path of the input file in S3, e.g. "pierre/inputs/recorded/New_file.webm"
        username: username string

    Returns:
        str: S3 prefix of the analysis folder, e.g.
             "pierre/outputs/recorded/New_file.webm/analysis/"
    """
    if file_key.startswith(f'{username}/inputs/'):
        relative_path = file_key[len(f'{username}/inputs/') :]
    else:
        # fallback in case file_key is not under inputs/
        relative_path = os.path.basename(file_key)

    relative_no_ext, _ = os.path.splitext(relative_path)
    return f'{username}/outputs/{relative_no_ext}/analysis/'


def s3_viz_exists(s3_client, bucket: str, file_key: str, username: str) -> bool:
    """
    Return True if a _viz.json exists for the given file in S3.
    """
    prefix = get_analysis_prefix(file_key, username)
    file_stem, _ = os.path.splitext(os.path.basename(file_key))
    viz_key = f'{prefix}{file_stem}_viz.json'

    try:
        s3_client.head_object(Bucket=bucket, Key=viz_key)
        return True
    except s3_client.exceptions.ClientError:
        return False


def list_viz_files(s3_client, bucket: str, file_key: str, username: str) -> list:
    """
    List all _viz.json files for a given input file.
    """
    prefix = get_analysis_prefix(file_key, username)
    objs = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix).get('Contents', [])
    return [obj['Key'] for obj in objs if obj['Key'].endswith('_viz.json')]


def get_exif_data(image_bytes):
    """Extract EXIF metadata from an image."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif_data = img._getexif() or {}
        exif = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            exif[tag] = value
        return exif
    except Exception as e:
        print(f'Error reading EXIF: {e}')
        return {}


def get_gps_from_exif(exif):
    """Return GPS coordinates in decimal if available."""
    if 'GPSInfo' not in exif:
        return None, None

    gps_info = exif['GPSInfo']
    gps_data = {}
    for t in gps_info:
        sub_tag = GPSTAGS.get(t, t)
        gps_data[sub_tag] = gps_info[t]

    def convert_to_decimal(coord, ref):
        """Convert GPS tuple to decimal degrees."""
        degrees = coord[0][0] / coord[0][1]
        minutes = coord[1][0] / coord[1][1]
        seconds = coord[2][0] / coord[2][1]
        dec = degrees + minutes / 60 + seconds / 3600
        if ref in ['S', 'W']:
            dec = -dec
        return dec

    lat = convert_to_decimal(gps_data['GPSLatitude'], gps_data['GPSLatitudeRef'])
    lon = convert_to_decimal(gps_data['GPSLongitude'], gps_data['GPSLongitudeRef'])
    return lat, lon


def get_decimal_from_dms(dms, ref):
    """Convert GPS coordinates in EXIF format to decimal degrees."""
    degrees, minutes, seconds = dms
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in ['S', 'W']:
        decimal = -decimal
    return decimal


def extract_lat_lon(gps_data):
    """Extract decimal lat/lon from EXIF GPSInfo dict."""
    try:
        lat = get_decimal_from_dms(gps_data['GPSLatitude'], gps_data['GPSLatitudeRef'])
        lon = get_decimal_from_dms(
            gps_data['GPSLongitude'], gps_data['GPSLongitudeRef']
        )
        return lat, lon
    except KeyError:
        return None, None


def get_images_with_gps(
    s3_client, bucket_name: str, file_keys: List[str], url_ttl: int = 900
) -> List[Dict]:
    """
    Return a list of dicts with *fresh* image URL and GPS coordinates (if available).
    - Lat/Lon are cached in S3 (thumbnails/gps_data.json).
    - Presigned URLs are generated on every call and NOT stored in S3.
    """
    # First, check in-memory lat/lon cache
    cache_key = (bucket_name, tuple(sorted(file_keys)))
    if cache_key in _gps_mem_cache:
        # Re-use lat/lon but refresh URLs each call
        coords_only = _gps_mem_cache[cache_key]
        images_with_gps = []
        for item in coords_only:
            thumb_key = get_thumbnail_key(item['key'])
            fresh_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': thumb_key},
                ExpiresIn=url_ttl,
            )
            images_with_gps.append({**item, 'url': fresh_url})
        return images_with_gps

    gps_cache_key = 'thumbnails/gps_data.json'

    # --- Load existing lat/lon cache from S3 ---
    try:
        obj = s3_client.get_object(Bucket=bucket_name, Key=gps_cache_key)
        gps_cache = json.load(obj['Body'])
    except s3_client.exceptions.NoSuchKey:
        gps_cache = {}
    except Exception:
        gps_cache = {}

    updated = False  # track if we need to write back

    def _convert_to_degrees(value):
        d, m, s = value
        return float(d) + float(m) / 60 + float(s) / 3600

    for key in file_keys:
        # Skip if we already have lat/lon
        if key in gps_cache and all(k in gps_cache[key] for k in ('lat', 'lon')):
            continue

        # Extract GPS from image if needed
        try:
            obj = s3_client.get_object(Bucket=bucket_name, Key=key)
            img_bytes = obj['Body'].read()
            img = Image.open(io.BytesIO(img_bytes))
            exif_data = img._getexif() or {}
            exif = {ExifTags.TAGS.get(t, t): v for t, v in exif_data.items()}
            gps_info = exif.get('GPSInfo')
            if not gps_info:
                continue

            gps_tags = {ExifTags.GPSTAGS.get(t, t): v for t, v in gps_info.items()}
            if 'GPSLatitude' not in gps_tags or 'GPSLongitude' not in gps_tags:
                continue

            lat = _convert_to_degrees(gps_tags['GPSLatitude'])
            lon = _convert_to_degrees(gps_tags['GPSLongitude'])
            if gps_tags.get('GPSLatitudeRef', 'N') == 'S':
                lat = -lat
            if gps_tags.get('GPSLongitudeRef', 'E') == 'W':
                lon = -lon

            # Store only coordinates in persistent cache
            gps_cache[key] = {'lat': lat, 'lon': lon}
            updated = True
        except Exception as e:
            print(f'Error processing {key}: {e}')

    # --- Persist new lat/lon if needed ---
    if updated:
        try:
            gps_json_bytes = json.dumps(gps_cache).encode('utf-8')
            s3_client.put_object(
                Bucket=bucket_name, Key=gps_cache_key, Body=gps_json_bytes
            )
        except Exception as e:
            print(f'Error updating gps_data.json: {e}')

    # --- Build final list with fresh URLs ---
    coords_only = []
    images_with_gps = []
    for key in file_keys:
        data = gps_cache.get(key)
        if not data:
            continue

        coords_only.append({'key': key, 'lat': data['lat'], 'lon': data['lon']})

        thumb_key = get_thumbnail_key(key)
        fresh_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': thumb_key},
            ExpiresIn=url_ttl,
        )
        images_with_gps.append(
            {'key': key, 'lat': data['lat'], 'lon': data['lon'], 'url': fresh_url}
        )

    # Cache only coordinates in memory for faster subsequent calls
    _gps_mem_cache[cache_key] = coords_only

    return images_with_gps


def build_gallery_map_with_gps(
    images_with_gps: list[dict], selected_key: str | None = None
):
    """
    Build a Dash layout with a Mapbox scatter plot of images that have GPS coordinates.
    - images_with_gps must contain dicts with keys: ['key', 'lat', 'lon', 'url']
    - selected_key highlights the currently selected image (if any).
    """
    if not images_with_gps:
        return html.Div('No images with GPS data.')

    # Filter to valid coordinates
    images_with_coords = [
        img
        for img in images_with_gps
        if isinstance(img.get('lat'), (int, float))
        and isinstance(img.get('lon'), (int, float))
    ]
    if not images_with_coords:
        return html.Div('No images with GPS data.')

    # Prepare data
    lats = [img['lat'] for img in images_with_coords]
    lons = [img['lon'] for img in images_with_coords]
    keys = [img['key'] for img in images_with_coords]
    filenames = [key.split('/')[-1] for key in keys]
    urls = [img['url'] for img in images_with_coords]
    colors = ['green' if key == selected_key else 'blue' for key in keys]

    # Create the map figure
    fig = go.Figure(
        go.Scattermapbox(
            lat=lats,
            lon=lons,
            mode='markers',
            marker=go.scattermapbox.Marker(size=14, color=colors),
            hovertext=filenames,
            hoverinfo='text',
            # Pass fresh presigned URLs as customdata for callbacks
            customdata=urls,
        )
    )

    fig.update_layout(
        mapbox=dict(
            style='open-street-map',
            center=dict(lat=sum(lats) / len(lats), lon=sum(lons) / len(lons)),
            zoom=3,
        ),
        margin={'r': 0, 't': 0, 'l': 0, 'b': 0},
        hovermode='closest',
    )

    # Layout container: map on the left, preview on the right
    return html.Div(
        style={
            'display': 'flex',
            'flexWrap': 'wrap',  # responsive wrapping on small screens
            'gap': '20px',
            'width': '100%',
        },
        children=[
            dcc.Graph(
                id='gallery-map',
                figure=fig,
                style={
                    'flex': '2 1 400px',  # grow/shrink, base width 400px
                    'minWidth': '300px',
                },
                config={'displayModeBar': False},  # cleaner look
            ),
            html.Div(
                id='map-image-preview',
                style={
                    'flex': '1 1 300px',
                    'minWidth': '200px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center',
                    'padding': '10px',
                },
                children='Click a marker to preview the image.',
            ),
        ],
    )


@cached(_s3_cache, key=lambda c, b, f=None: hashkey('list_files_in_s3', b, f))
def _cached_list_files_in_s3(s3_client, bucket_name: str, folder_name: Optional[str]):
    """Cached raw S3 list_objects_v2 call."""
    prefix = f"{folder_name.strip().rstrip('/')}/" if folder_name else ''
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    files = response.get('Contents', [])
    return [obj['Key'] for obj in files if not obj['Key'].endswith('/')]


@cached(_s3_cache, key=lambda c, b: hashkey('list_s3_folders', b))
def _cached_list_s3_folders(s3_client, bucket_name: str):
    """Cached folder list using Delimiter='/'."""
    response = s3_client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
    prefixes = response.get('CommonPrefixes', [])
    return [p['Prefix'].rstrip('/') for p in prefixes]


def invalidate_s3_cache(bucket_name: str, folder_name: Optional[str] = None):
    """Clear cached results for a specific bucket/folder."""
    # Invalidate folder listing cache
    _s3_cache.pop(hashkey('list_s3_folders', bucket_name), None)

    # Normalize folder_name: treat "" and None the same
    folder_key = folder_name if folder_name else None
    _s3_cache.pop(hashkey('list_files_in_s3', bucket_name, folder_key), None)


def list_root_files(s3_client, bucket_name):
    """
    Return only files at the root (top-level) of the bucket.
    If bucket_name is missing or inaccessible, return a message instead of raising.
    """
    # Check for a missing/empty bucket name first
    if not bucket_name:
        return {
            'error': '⚠️ No bucket access now: please select a bucket or contact an admin.'
        }

    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Delimiter='/',
        )
        files = response.get('Contents', [])
        return [obj['Key'] for obj in files if not obj['Key'].endswith('/')]

    except Exception as e:
        # Catch AWS/boto errors and return a clean message
        print(f'S3 list error for bucket {bucket_name}: {e}')
        return {
            'error': '⚠️ No bucket access now: please try again later or contact an admin.'
        }
