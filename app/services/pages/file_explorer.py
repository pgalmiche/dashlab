import base64
import logging
from datetime import datetime
from typing import List, Optional, Union

import boto3
import dash
import dash.dash_table as dt
from dash import callback, callback_context, ctx, dcc, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)

dash.register_page(__name__, path="/file-explorer", name="S3 File Explorer", order=1)

MONGO_URI = (
    f"mongodb://{settings.mongo_initdb_root_username}:"
    f"{settings.mongo_initdb_root_password}@mongo_db:27017/"
    f"{settings.mongo_initdb_database}?authSource=admin"
)

# AWS S3 Configuration
S3_BUCKET_NAME = "personnal-files-pg"
AWS_REGION = "us-east-1"


def generate_s3_url(bucket: str, key: str, region: str) -> str:
    """
    Generate the public S3 URL for an object.

    :param bucket: S3 bucket name
    :param key: Object key (path + filename)
    :param region: AWS region of the bucket
    :return: Public URL string
    """
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{key}"
    else:
        return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def generate_presigned_url(
    bucket_name: str, object_key: str, expiration: int = 3600
) -> str:
    """
    Generate a pre-signed S3 URL for secure file access.

    Args:
        bucket_name (str): S3 bucket name.
        object_key (str): Path to the file in the bucket.
        expiration (int): URL validity period in seconds (default: 1 hour).

    Returns:
        str: Pre-signed URL, or None if generation fails.
    """
    import boto3
    from botocore.exceptions import ClientError

    s3_client = boto3.client("s3", region_name="us-east-1")  # Set region here if needed

    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_key},
            ExpiresIn=expiration,  # ✅ Must be an int, e.g., 3600
        )
        print(f"[✅] Pre-signed URL: {response}")
        return response
    except ClientError as e:
        print(f"[❌] Failed to generate pre-signed URL: {e}")
        return None


def get_collection():
    """
    Get MongoDB collection for file metadata.

    :return: pymongo Collection object or None if connection fails
    """
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")  # Test connection
        db = client.get_database()
        return db["file_metadata"]
    except ServerSelectionTimeoutError:
        logger.info("Warning: Could not connect to MongoDB.")
        return None


# Initialize boto3 S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=AWS_REGION,
)


def list_s3_folders() -> List[str]:
    """
    List top-level folders in the S3 bucket.

    :return: List of folder names (strings), including empty string for root
    """
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Delimiter="/")
        prefixes = response.get("CommonPrefixes", [])
        folders = [p["Prefix"].rstrip("/") for p in prefixes]
        return [""] + folders  # Include root folder as empty string
    except Exception as e:
        logger.error(f"Failed to list S3 folders: {e}")
        return []


# Page layout definition
layout = html.Div(
    [
        html.H2("Upload Files"),
        html.Label("Storage is done on S3 buckets:"),
        html.Br(),
        html.Br(),
        html.Label("Select Existing Folder:"),
        dcc.Dropdown(
            id="folder-dropdown",
            options=[{"label": f, "value": f} for f in list_s3_folders()],
            placeholder="Select a folder (optional)",
            clearable=True,
            style={"width": "300px"},
        ),
        html.Br(),
        html.Label("Or Create New Folder:"),
        dcc.Input(
            id="new-folder-name",
            type="text",
            placeholder="Enter new folder name (optional)",
            style={"width": "300px"},
        ),
        html.Br(),
        html.Br(),
        dcc.Input(
            id="file-tags", type="text", placeholder="Enter tags (comma-separated)"
        ),
        html.Br(),
        html.Br(),
        dcc.Upload(
            id="upload-files", children=html.Button("Upload File"), multiple=True
        ),
        html.Br(),
        html.Div(id="upload-status"),
        html.Div(id="tags-status"),
        html.Div(id="uploaded-files-list"),
        html.Br(),
        html.Br(),
        html.H3("Database Entries"),
        html.Div(id="database-entries-list"),
        html.Label("Enter file paths to Delete (comma-separated):"),
        html.Br(),
        html.Br(),
        dcc.Input(
            id="delete-paths-input",
            type="text",
            placeholder="Enter file paths to delete",
        ),
        html.Br(),
        html.Br(),
        html.Button("Delete Selected Entries", id="delete-btn", n_clicks=0),
        html.Br(),
        html.Br(),
        html.Button("Refresh Table", id="refresh-btn", n_clicks=0),
        html.Hr(),
        html.H2("Select and Edit Existing Files"),
        html.Label("Select a Folder:"),
        dcc.Dropdown(
            id="folder-selector",
            options=[{"label": "(No Folder)", "value": ""}]
            + [{"label": f, "value": f} for f in list_s3_folders() if f != ""],
            placeholder="Select a folder",
            clearable=True,
            style={"width": "300px"},
        ),
        html.Br(),
        html.Label("Select a File:"),
        dcc.Dropdown(
            id="file-selector",
            placeholder="Select a file",
            style={"width": "600px"},
            clearable=True,
        ),
        html.Br(),
        html.Div(id="file-display"),
        html.Br(),
        html.Label("Edit Tags (comma-separated):"),
        dcc.Input(id="edit-tags", type="text", style={"width": "600px"}),
        html.Br(),
        html.Br(),
        html.Label("Change Folder:"),
        dcc.Dropdown(
            id="edit-folder-dropdown",
            options=[{"label": f, "value": f} for f in list_s3_folders()],
            placeholder="Select folder",
            clearable=True,
            style={"width": "300px"},
        ),
        html.Br(),
        html.Label("Or create new folder:"),
        dcc.Input(
            id="edit-new-folder",
            type="text",
            placeholder="Enter new folder name",
            style={"width": "300px"},
        ),
        html.Br(),
        html.Br(),
        html.Button("Update File Metadata & Location", id="update-file-btn"),
        html.Div(id="update-status"),
    ]
)


def save_file(
    decoded_content: bytes, filename: str, folder_name: Optional[str] = None
) -> str:
    """
    Save a file to S3 with an optional folder prefix.

    :param decoded_content: File content as bytes
    :param filename: Name of the file
    :param folder_name: Optional folder prefix within the bucket
    :return: Public URL of the saved file
    """
    if folder_name:
        folder_name = folder_name.strip().strip("/")
        key = f"{folder_name}/{filename}"
    else:
        key = filename

    s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=key, Body=decoded_content)
    s3_url = generate_s3_url(S3_BUCKET_NAME, key, AWS_REGION)
    return s3_url


def store_file_metadata(file_path: str, tags: List[str]) -> None:
    """
    Store file metadata in MongoDB.

    :param file_path: URL or path of the stored file
    :param tags: List of tags associated with the file
    """
    collection = get_collection()
    if collection is None:
        logger.info("Skipping metadata storage: no DB connection.")
        return
    file_entry = {
        "file_path": file_path,
        "tags": tags,
        "timestamp": datetime.utcnow(),
    }
    collection.insert_one(file_entry)


def delete_file_from_s3(filename: str) -> None:
    """
    Delete a file from S3.

    :param filename: Object key (path + filename) in S3
    """
    try:
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=filename)
        logger.info(f"Deleted {filename} from S3.")
    except Exception as e:
        logger.error(f"Error deleting {filename} from S3: {e}")


def delete_entries_by_path(paths_to_delete: List[str]) -> None:
    """
    Delete files from S3 and remove their metadata from MongoDB.

    :param paths_to_delete: List of file paths (URLs) to delete
    """
    collection = get_collection()
    if collection is None:
        logger.info("Skipping deletion: no DB connection.")
        return

    for file_path in paths_to_delete:
        if file_path.startswith("https://"):
            # Extract S3 key from URL
            parts = file_path.split("/")
            filename = "/".join(parts[3:])  # bucket + region parts removed
            delete_file_from_s3(filename)
        else:
            logger.warning(f"Invalid file path for deletion: {file_path}")

    collection.delete_many({"file_path": {"$in": paths_to_delete}})


def fetch_all_files() -> List[dict]:
    """
    Fetch all file metadata entries from MongoDB.

    :return: List of file metadata dicts
    """
    collection = get_collection()
    if collection is None:
        logger.info("Skipping fetch: no DB connection.")
        return []
    return list(collection.find({}, {"_id": 0}))


########################### Callbacks ##############################


@callback(
    Output("upload-status", "children"),
    Output("tags-status", "children"),
    Output("uploaded-files-list", "children"),
    Input("upload-files", "contents"),
    State("upload-files", "filename"),
    State("folder-dropdown", "value"),
    State("new-folder-name", "value"),
    State("file-tags", "value"),
)
def upload_files(
    file_contents: Optional[List[str]],
    filenames: Optional[List[str]],
    selected_folder: Optional[str],
    new_folder_name: Optional[str],
    file_tags: Optional[str],
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
        tags_list = [tag.strip() for tag in file_tags.split(",") if tag.strip()]

    uploaded_filenames = []

    for content, filename in zip(file_contents, filenames):
        try:
            content_type, content_string = content.split(",")
            decoded = base64.b64decode(content_string)
            file_url = save_file(decoded, filename, folder_name)
            store_file_metadata(file_url, tags_list)
            uploaded_filenames.append(filename)
            logger.info(f"Uploaded {filename} to folder {folder_name or '(root)'}")
        except Exception as e:
            logger.error(f"Error uploading file {filename}: {e}")
            return (
                f"Error uploading {filename}: {e}",
                "",
                html.Ul([html.Li(filename) for filename in uploaded_filenames]),
            )

    status_msg = f"Successfully uploaded {len(uploaded_filenames)} file(s)."
    tags_msg = (
        f"Tags applied: {', '.join(tags_list)}" if tags_list else "No tags applied."
    )
    return status_msg, tags_msg, html.Ul([html.Li(f) for f in uploaded_filenames])


@callback(
    Output("database-entries-list", "children"),
    Input("refresh-btn", "n_clicks"),
    Input("delete-btn", "n_clicks"),
    State("delete-paths-input", "value"),
    prevent_initial_call=True,
)
def update_database_entries(
    refresh_clicks: int, delete_clicks: int, delete_paths: Optional[str]
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
    triggered_id = callback_context.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "delete-btn":
        if not delete_paths:
            return html.Div("Please enter file paths to delete.")
        paths_to_delete = [p.strip() for p in delete_paths.split(",") if p.strip()]
        if not paths_to_delete:
            return html.Div("No valid paths provided for deletion.")
        delete_entries_by_path(paths_to_delete)
        logger.info(f"Deleted entries for paths: {paths_to_delete}")

    files = fetch_all_files()

    if not files:
        return html.Div("No file entries found in database.")

    # Build table headers dynamically from keys of first entry
    columns = list(files[0].keys())
    table_header = [html.Th(col) for col in columns]

    # Build table rows
    table_rows = []
    for file in files:
        row = [html.Td(file.get(col, "")) for col in columns]
        table_rows.append(html.Tr(row))

    return html.Table(
        [html.Thead(html.Tr(table_header)), html.Tbody(table_rows)],
        style={"border": "1px solid black", "borderCollapse": "collapse"},
    )


@callback(
    Output("file-selector", "options"),
    Input("folder-selector", "value"),
)
def update_file_selector_options(folder_name: Optional[str]) -> List[dict]:
    """
    Update the file dropdown options based on the selected folder.

    :param folder_name: Selected folder name or empty string for root
    :return: List of options dicts for dcc.Dropdown
    """
    prefix = f"{folder_name.strip()}/" if folder_name else ""
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=prefix)
        files = response.get("Contents", [])
        file_keys = [obj["Key"] for obj in files if not obj["Key"].endswith("/")]
        options = [{"label": key[len(prefix) :], "value": key} for key in file_keys]
        return options
    except Exception as e:
        logger.error(f"Error listing files in folder '{folder_name}': {e}")
        return []


def is_image(file_key: str) -> bool:
    return file_key.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"))


def is_pdf(file_key: str) -> bool:
    return file_key.lower().endswith(".pdf")


def is_audio(file_key: str) -> bool:
    return file_key.lower().endswith((".mp3", ".wav", ".ogg"))


@callback(
    Output("file-display", "children"),
    Output("edit-tags", "value"),
    Output("edit-folder-dropdown", "value"),
    Output("edit-new-folder", "value"),
    Input("file-selector", "value"),
)
def display_selected_file(
    file_key: Optional[str],
) -> tuple[html.Div, str, Optional[str], str]:
    if not file_key:
        return html.Div("No file selected."), "", None, ""

    file_url = generate_presigned_url(S3_BUCKET_NAME, file_key)

    logging.info(f"Generated url: {file_url}")

    # Determine file type and render appropriately
    if is_image(file_key):
        display_component = html.Img(src=file_url, style={"maxWidth": "100%"})
    elif is_pdf(file_key):
        display_component = html.Iframe(
            src=file_url, style={"width": "100%", "height": "600px"}
        )
    elif is_audio(file_key):
        display_component = html.Audio(src=file_url, controls=True)
    else:
        display_component = html.A("Download file", href=file_url, target="_blank")

    # Fetch tags from database
    collection = get_collection()
    metadata = collection.find_one({"file_path": {"$regex": file_key}})
    tags = ", ".join(metadata.get("tags", [])) if metadata else ""

    folder_name = "/".join(file_key.split("/")[:-1]) if "/" in file_key else ""

    return html.Div([display_component]), tags, folder_name or None, ""


@callback(
    Output("update-status", "children"),
    Input("update-file-btn", "n_clicks"),
    State("file-selector", "value"),
    State("edit-tags", "value"),
    State("edit-folder-dropdown", "value"),
    State("edit-new-folder", "value"),
    prevent_initial_call=True,
)
def update_file_metadata(
    n_clicks: int,
    selected_file_key: Optional[str],
    new_tags: Optional[str],
    selected_folder: Optional[str],
    new_folder_name: Optional[str],
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
        return "No file selected to update."

    collection = get_collection()
    if collection is None:
        return "Database connection not available."

    # Prepare tags list
    tags_list = []
    if new_tags:
        tags_list = [tag.strip() for tag in new_tags.split(",") if tag.strip()]

    # Determine new folder path
    target_folder = (
        new_folder_name.strip() if new_folder_name else selected_folder or ""
    )

    old_key = selected_file_key
    filename = old_key.split("/")[-1]

    # If folder changed, move file in S3
    if target_folder and target_folder.strip() != "/".join(old_key.split("/")[:-1]):
        new_key = f"{target_folder.strip().rstrip('/')}/{filename}"
        try:
            # Copy old object to new key
            s3_client.copy_object(
                Bucket=S3_BUCKET_NAME,
                CopySource={"Bucket": S3_BUCKET_NAME, "Key": old_key},
                Key=new_key,
            )
            # Delete old object
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=old_key)
            logger.info(f"Moved file from {old_key} to {new_key}")
        except Exception as e:
            logger.error(f"Error moving file in S3: {e}")
            return f"Error moving file: {e}"
    else:
        new_key = old_key

    new_file_url = generate_s3_url(S3_BUCKET_NAME, new_key, AWS_REGION)

    # Update DB entry
    update_result = collection.update_one(
        {"file_path": generate_s3_url(S3_BUCKET_NAME, old_key, AWS_REGION)},
        {
            "$set": {
                "file_path": new_file_url,
                "tags": tags_list,
                "timestamp": datetime.utcnow(),
            }
        },
    )

    if update_result.matched_count == 0:
        return "File metadata not found in database."

    return "File metadata and location updated successfully."
