import base64
import io
import os
import uuid
from datetime import datetime

import boto3
import dash
import dash.dash_table as dt
from dash import callback, dcc, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from config.logging import setup_logging

setup_logging()
import logging

logger = logging.getLogger(__name__)

from config.settings import settings

dash.register_page(__name__, path="/file-explorer", name="S3 File Explorer", order=1)

MONGO_URI = (
    f"mongodb://{settings.mongo_initdb_root_username}:"
    f"{settings.mongo_initdb_root_password}@mongo_db:27017/"
    f"{settings.mongo_initdb_database}?authSource=admin"
)


def get_collection():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client.get_database()
        return db["file_metadata"]
    except ServerSelectionTimeoutError:
        logger.info("Warning: Could not connect to MongoDB.")
        return None


# AWS S3 Configuration
S3_BUCKET_NAME = "personnal-files-pg"
AWS_REGION = "us-east-1"

# Load environment variables from .env file
load_dotenv()

# Read AWS credentials from environment
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")

# Initialize boto3 S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


# Helper: List existing folders in S3 bucket
def list_s3_folders():
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Delimiter="/")
        prefixes = response.get("CommonPrefixes", [])
        folders = [p["Prefix"].rstrip("/") for p in prefixes]
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
    s3_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
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


# Callback to handle file upload
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

    for content, filename in zip(files_contents, filenames):
        content_type, content_string = content.split(",")
        decoded = base64.b64decode(content_string)

        # Save file in chosen folder
        file_path = save_file(decoded, filename, folder_to_use)

        # Store metadata in MongoDB
        store_file_metadata(file_path, tags.split(",") if tags else [])

        status_messages.append(f"File '{filename}' uploaded successfully!")

    # Fetch all uploaded files from MongoDB
    uploaded_files = fetch_all_files()

    return (
        status_messages,
        f"Tags for the file(s): {tags}",
        html.Ul(
            [
                html.Li(
                    f"File: {file['file_path']} | Tags: {', '.join(file['tags'])} | Uploaded on: {file['timestamp']}"
                )
                for file in uploaded_files
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
