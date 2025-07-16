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

dash.register_page(
    __name__, path="/file-explorer", name=("MongoDB File Explorer",), order=2
)

# MongoDB connection settings
MONGO_URI = "mongodb://mongo_admin:StrongPassword123!@mongo_db:27017/mydatabase?authSource=admin"
client = MongoClient(MONGO_URI)
db = client.get_database()
collection = db["file_metadata"]

# Folder to store uploaded files
UPLOAD_FOLDER = "./uploaded_files/"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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

# Layout of the page
layout = html.Div(
    [
        html.H2("Upload Files"),
        # Storage Option (Local or S3)
        html.Label("Storage Option:"),
        html.Br(),
        html.Br(),
        dcc.RadioItems(
            id="storage-option",
            options=[
                {"label": "Local Storage", "value": "local"},
                {"label": "Amazon S3", "value": "s3"},
            ],
            value="local",  # Default to local
            inline=True,
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


# Function to save file locally or upload to S3
def save_file(decoded_content, filename, storage_option):
    if storage_option == "local":
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(save_path, "wb") as f:
            f.write(decoded_content)
        return save_path  # Return local path

    elif storage_option == "s3":
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=filename, Body=decoded_content)
        s3_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{filename}"
        return s3_url  # Return S3 URL


# Function to store metadata in MongoDB
def store_file_metadata(file_path, tags):
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
        print(f"Deleted {filename} from S3.")
    except Exception as e:
        print(f"Error deleting {filename} from S3: {e}")


# Function to delete files locally
def delete_file_locally(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)


# Function to delete files based on their path (local or S3)
def delete_entries_by_path(paths_to_delete):
    for file_path in paths_to_delete:
        if file_path.startswith("https://"):  # S3 file
            filename = file_path.split("/")[-1]
            delete_file_from_s3(filename)
        else:
            delete_file_locally(file_path)

    collection.delete_many({"file_path": {"$in": paths_to_delete}})


# Fetch all file metadata from MongoDB
def fetch_all_files():
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
    State("storage-option", "value"),  # New: Local or S3
)
def upload_files(files_contents, filenames, tags, storage_option):
    if files_contents:
        status_messages = []

        for content, filename in zip(files_contents, filenames):
            content_type, content_string = content.split(",")
            decoded = base64.b64decode(content_string)

            # Save file (locally or to S3)
            file_path = save_file(decoded, filename, storage_option)

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

    return "", "", ""


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

    # Convert MongoDB data to a format compatible with DataTable
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
        data=df_data,  # Data to display
        style_table={"overflowX": "auto"},  # Responsive table
        style_header={
            "backgroundColor": "black",
            "color": "white",
            "fontWeight": "bold",
            "textAlign": "center",
        },
        style_cell={"textAlign": "left", "padding": "5px"},
        style_data_conditional=[
            {
                "if": {"row_index": "odd"},
                "backgroundColor": "#f9f9f9",
            }
        ],
        page_size=10,  # Pagination (10 rows per page)
        sort_action="native",  # Enable sorting
        filter_action="native",  # Enable filtering
    )

    # Handle deletions
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
        return table  # Refresh the table

    return table  # Initially render the table
