import os

import dash
from dash import callback, callback_context, dcc, html
from dash.dependencies import Input, Output, State

dash.register_page(__name__, path="/k3d", name=("3D views",), order=4)

####################### WIDGETS ################################
# List all files in the directory
directory = "./"
all_files = os.listdir(directory)

# Filter HTML files
html_files = [file for file in all_files if file.endswith(".html")]
# Create dropdown options from the list of HTML files
dropdown_options = [{"label": file, "value": file} for file in all_files]

dd = dcc.Dropdown(
    id="file-dropdown", options=all_files, value=all_files[0], clearable=False
)

####################### PAGE LAYOUT #############################
layout = html.Div(
    children=[
        html.H2("Explore html files and display them", className="fw-bold text-center"),
        # Text input for directory path
        dcc.Input(
            id="directory-input",
            type="text",
            placeholder="Enter directory path",
            style={"width": "400px"},
        ),
        # Button to load files
        html.Button("Load Files", id="load-button", n_clicks=0),
        # Button to load files
        dd,
        html.Div(id="file-chosen"),
        # dcc.Graph(id="3dvisu"),
    ]
)


# Define a combined callback to handle both the dropdown update and content display
@callback(
    [
        Output("file-dropdown", "options"),
        Output("file-chosen", "children"),
        Output("file-dropdown", "value"),
    ],
    [Input("load-button", "n_clicks"), Input("file-dropdown", "value")],
    [State("directory-input", "value")],
)
def update_dropdown_and_display(n_clicks, selected_file, directory):
    ctx = callback_context

    # Determine which input triggered the callback
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if triggered_id == "load-button" and directory:
        if os.path.exists(directory) and os.path.isdir(directory):
            # List HTML files in the directory
            html_files = [
                file for file in os.listdir(directory) if file.endswith(".html")
            ]
            # Create dropdown options
            dropdown_options = [
                {"label": file, "value": os.path.join(directory, file)}
                for file in html_files
            ]
            return (
                dropdown_options,
                "",
                None,
            )  # Clear the display and dropdown selection
        else:
            return [], f"Invalid directory: {directory}", None

    elif triggered_id == "file-dropdown" and selected_file:
        # Read the HTML file content
        with open(selected_file, "r", encoding="utf-8") as file:
            html_content = file.read()
        return (
            dash.no_update,
            html.Iframe(
                srcDoc=html_content,
                style={"width": "100%", "height": "600px", "border": "none"},
            ),
            selected_file,
        )

    return [], "No directory loaded or file selected", None
