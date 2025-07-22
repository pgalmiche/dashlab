import base64
import logging
from datetime import datetime

import boto3
import dash
import dash.dash_table as dt
from dash import ctx  # for context in callbacks
from dash import callback, dcc, html
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


def generate_s3_url(bucket, key, region):
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{key}"
    else:
        return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def generate_presigned_url(bucket, key, expiration=3600):
    """
    Generate a pre-signed URL to share an S3 object.

    :param bucket: S3 bucket name
    :param key: S3 object key (path/filename)
    :param expiration: Time in seconds for URL to remain valid (default 1 hour)
    :return: pre-signed URL as string
    """
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )
        return url
    except Exception as e:
        logger.error(f"Error generating pre-signed URL for {key}: {e}")
        return None


def get_collection():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
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
    region_name=settings.aws_region,
)


def list_s3_folders():
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Delimiter="/")
        prefixes = response.get("CommonPrefixes", [])
        folders = [p["Prefix"].rstrip("/") for p in prefixes]
        # Add a special option for files in the root (no folder)
        folders = [""] + folders  # empty string for root
        return folders
    except Exception as e:
        logger.error(f"Failed to list S3 folders: {e}")
        return []


# Layout of the page
layout = html.Div(
    [
        html.H2("Upload Files"),
        html.Label("Storage is done on S3 buckets:"),
        html.Br(),
        html.Br(),
        # Dropdown for existing folders
        html.Label("Select Existing Folder:"),
        dcc.Dropdown(
            id="folder-dropdown",
            options=[{"label": f, "value": f} for f in list_s3_folders()],
            placeholder="Select a folder (optional)",
            clearable=True,
            style={"width": "300px"},
        ),
        html.Br(),
        # Or input new folder name
        html.Label("Or Create New Folder:"),
        dcc.Input(
            id="new-folder-name",
            type="text",
            placeholder="Enter new folder name (optional)",
            style={"width": "300px"},
        ),
        html.Br(),
        html.Br(),
        # Tags Input
        dcc.Input(
            id="file-tags", type="text", placeholder="Enter tags (comma-separated)"
        ),
        html.Br(),
        html.Br(),
        # File Upload
        dcc.Upload(
            id="upload-files", children=html.Button("Upload File"), multiple=True
        ),
        html.Br(),
        # Display Status Messages
        html.Div(id="upload-status"),
        html.Div(id="tags-status"),
        # List of Uploaded Files
        html.Div(id="uploaded-files-list"),
        # Database Entries
        html.Br(),
        html.Br(),
        html.H3("Database Entries"),
        html.Div(id="database-entries-list"),
        # Deletion Input
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
        # Delete and Refresh Buttons
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


# Function to save file to S3 with optional folder prefix
def save_file(decoded_content, filename, folder_name=None):
    if folder_name:
        folder_name = folder_name.strip().strip("/")
        key = f"{folder_name}/{filename}"
    else:
        key = filename

    s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=key, Body=decoded_content)
    s3_url = generate_s3_url(S3_BUCKET_NAME, key, AWS_REGION)
    return s3_url


# Function to store metadata in MongoDB
def store_file_metadata(file_path, tags):
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


# Function to delete files from S3
def delete_file_from_s3(filename):
    try:
        s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=filename)
        logger.info(f"Deleted {filename} from S3.")
    except Exception as e:
        logger.error(f"Error deleting {filename} from S3: {e}")


# Function to delete files based on their path (S3 only now)
def delete_entries_by_path(paths_to_delete):
    collection = get_collection()
    if collection is None:
        logger.info("Skipping metadata storage: no DB connection.")
        return
    for file_path in paths_to_delete:
        if file_path.startswith("https://"):
            filename = "/".join(file_path.split("/")[3:])  # Remove domain and bucket
            delete_file_from_s3(filename)
        else:
            logger.warning(f"Invalid file path for deletion: {file_path}")

    collection.delete_many({"file_path": {"$in": paths_to_delete}})


# Fetch all file metadata from MongoDB
def fetch_all_files():
    collection = get_collection()
    if collection is None:
        logger.info("Skipping metadata storage: no DB connection.")
        return []
    return list(collection.find({}, {"_id": 0}))


####################### Callbacks #############################


@callback(
    Output("upload-status", "children"),
    Output("tags-status", "children"),
    Output("uploaded-files-list", "children"),
    Input("upload-files", "contents"),
    State("upload-files", "filename"),
    State("file-tags", "value"),
    State("folder-dropdown", "value"),
    State("new-folder-name", "value"),
)
def upload_files(files_contents, filenames, tags, selected_folder, new_folder):
    if files_contents is None:
        raise PreventUpdate

    # Decide which folder to use
    folder_to_use = None
    if new_folder and new_folder.strip():
        folder_to_use = new_folder.strip()
    elif selected_folder:
        folder_to_use = selected_folder

    status_messages = []
    uploaded_files_new = []

    for content, filename in zip(files_contents, filenames):
        content_type, content_string = content.split(",")
        decoded = base64.b64decode(content_string)

        # Save file in chosen folder (make sure save_file accepts folder)
        file_path = save_file(decoded, filename, folder_to_use)

        # Store metadata in MongoDB
        store_file_metadata(file_path, tags.split(",") if tags else [])

        status_messages.append(f"File '{filename}' uploaded successfully!")

        uploaded_files_new.append(
            {
                "file_path": file_path,
                "tags": tags.split(",") if tags else [],
                "timestamp": datetime.utcnow(),
            }
        )

    return (
        status_messages,
        f"Tags for the file(s): {tags}",
        html.Ul(
            [
                html.Li(
                    f"File: {file['file_path']} | Tags: {', '.join(file['tags'])} | Uploaded on: {file['timestamp']}"
                )
                for file in uploaded_files_new
            ]
        ),
    )


# Callback to display and delete database entries
@callback(
    Output("database-entries-list", "children"),
    [Input("delete-btn", "n_clicks"), Input("refresh-btn", "n_clicks")],
    State("delete-paths-input", "value"),
)
def display_and_delete_entries(delete_clicks, refresh_clicks, paths_input):
    entries = fetch_all_files()

    if not entries:
        return "No entries found in the database."

    df_data = [
        {
            "File Path": entry.get("file_path", "N/A"),
            "Tags": ", ".join(entry.get("tags", [])),
            "Upload Time": entry.get("timestamp", "N/A"),
        }
        for entry in entries
    ]

    table = dt.DataTable(
        columns=[
            {"name": "File Path", "id": "File Path"},
            {"name": "Tags", "id": "Tags"},
            {"name": "Upload Time", "id": "Upload Time"},
        ],
        data=df_data,
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "black",
            "color": "white",
            "fontWeight": "bold",
            "textAlign": "center",
        },
        style_cell={"textAlign": "left", "padding": "5px"},
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#f9f9f9"}
        ],
        page_size=10,
        sort_action="native",
        filter_action="native",
    )

    if delete_clicks > 0 and paths_input:
        paths_to_delete = [path.strip() for path in paths_input.split(",")]

        if paths_to_delete:
            delete_entries_by_path(paths_to_delete)
            return html.Div(
                [
                    html.P(f"{len(paths_to_delete)} entries deleted successfully."),
                    table,
                ]
            )

    if refresh_clicks > 0:
        return table

    return table


@callback(
    Output("file-display", "children"),
    Output("edit-tags", "value"),
    Output("edit-folder-dropdown", "value"),
    Output("edit-new-folder", "value"),
    Input("folder-selector", "value"),
    Input("file-selector", "value"),
)
def display_file_and_metadata(selected_folder, selected_file):
    if not selected_folder or not selected_file:
        return "", "", None, ""

    if selected_folder:
        full_key = f"{selected_folder}/{selected_file}"
    else:
        full_key = selected_file

    file_url = generate_presigned_url(S3_BUCKET_NAME, full_key)
    if not file_url:
        return "Failed to generate file URL.", "", None, ""

    collection = get_collection()
    if collection is None:
        return "No DB connection.", "", None, ""

    file_doc = collection.find_one({"file_path": file_url})
    if not file_doc:
        return "File metadata not found.", "", None, ""

    tags = ",".join(file_doc.get("tags", []))

    # Display image or pdf inline, else download link
    lower_path = file_url.lower()
    if any(
        lower_path.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]
    ):
        file_display = html.Img(
            src=file_url, style={"maxWidth": "600px", "maxHeight": "400px"}
        )
    elif lower_path.endswith(".pdf"):
        file_display = html.Iframe(
            src=file_url, style={"width": "600px", "height": "400px"}
        )
    else:
        file_display = html.A("Download File", href=file_url, target="_blank")

    return file_display, tags, selected_folder, ""


@callback(
    Output("file-selector", "options"),
    Output("file-selector", "value"),
    Input("refresh-btn", "n_clicks"),
    Input("folder-selector", "value"),
    prevent_initial_call=False,
)
def update_file_selector_options_and_files(refresh_clicks, selected_folder):
    triggered_id = ctx.triggered_id

    if triggered_id == "refresh-btn":
        # On refresh button click, fetch all files from DB and update options
        files = fetch_all_files()
        options = [
            {"label": file["file_path"], "value": file["file_path"]} for file in files
        ]
        # We can't guess a good value here, so just keep it None (no selection)
        return options, None

    elif triggered_id == "folder-selector":
        # Folder selected - list files in S3 folder or root if empty string
        prefix = (
            f"{selected_folder}/" if selected_folder else ""
        )  # empty prefix if root

        try:
            response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=prefix)
            contents = response.get("Contents", [])
            files = [
                obj["Key"].replace(prefix, "")
                for obj in contents
                if not obj["Key"].endswith("/")
            ]
            options = [{"label": f, "value": f} for f in files]
            return options, None
        except Exception as e:
            logger.error(f"Failed to list files in folder '{selected_folder}': {e}")
            return [], None

    # Fallback: no trigger or unknown trigger
    return [], None


@callback(
    Output("update-status", "children"),
    Input("update-file-btn", "n_clicks"),
    State("folder-selector", "value"),
    State("file-selector", "value"),
    State("edit-tags", "value"),
    State("edit-folder-dropdown", "value"),
    State("edit-new-folder", "value"),
    prevent_initial_call=True,
)
def update_file_metadata_and_location(
    n_clicks, current_folder, current_file, new_tags_str, selected_folder, new_folder
):
    if not current_folder or not current_file:
        return "No file selected."

    collection = get_collection()
    if collection is None:
        return "No DB connection."

    old_key = f"{current_folder}/{current_file}"
    old_file_path = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{old_key}"

    file_doc = collection.find_one({"file_path": old_file_path})
    if not file_doc:
        return "File metadata not found."

    # Determine new folder to move to
    folder_to_use = None
    if new_folder and new_folder.strip():
        folder_to_use = new_folder.strip()
    elif selected_folder:
        folder_to_use = selected_folder

    new_tags = [tag.strip() for tag in new_tags_str.split(",")] if new_tags_str else []

    new_key = old_key
    if folder_to_use:
        filename_only = current_file
        new_key = f"{folder_to_use}/{filename_only}"

    try:
        # Move file if folder changed
        if new_key != old_key:
            copy_source = {"Bucket": S3_BUCKET_NAME, "Key": old_key}
            s3_client.copy_object(
                Bucket=S3_BUCKET_NAME, CopySource=copy_source, Key=new_key
            )
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=old_key)

        new_file_path = (
            f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{new_key}"
        )

        # Update metadata
        collection.update_one(
            {"file_path": old_file_path},
            {
                "$set": {
                    "file_path": new_file_path,
                    "tags": new_tags,
                    "timestamp": datetime.utcnow(),
                }
            },
        )

        return "File metadata and location updated successfully."

    except Exception as e:
        logger.error(f"Error updating file metadata/location: {e}")
        return f"Error: {str(e)}"
