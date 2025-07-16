import os

import dash
import requests
from dash import callback, callback_context, dcc, html
from dash.dependencies import Input, Output, State

dash.register_page(
    __name__, path="/yt-search-api", name=("Youtube search API",), order=5
)

####################### WIDGETS ################################
SEARCH_URL = "http://api:80/search"


def fetch_youtube_results(query):
    params = {"query": query}
    response = requests.get(SEARCH_URL, params=params)
    return response.json()


####################### PAGE LAYOUT #############################
layout = html.Div(
    children=[
        html.H2("Queries for YT videos", className="fw-bold text-center"),
        # Text input for directory path
        dcc.Input(
            id="yt-api-query",
            type="text",
            placeholder="Enter query for Youtube API:",
            style={"width": "500px"},
        ),
        # Button to load files
        html.Button("Send request", id="yt-api-call", n_clicks=0),
        # Button to load files
        html.Div(id="yt-api-response"),
    ]
)


# Define a combined callback to handle both the dropdown update and content display
@callback(
    Output("yt-api-response", "children"),
    Input("yt-api-call", "n_clicks"),
    State("yt-api-query", "value"),
)
def show_api_response_from_query(n_clicks, query):
    if n_clicks == 0:
        return ""  # Empty initially

    if not query:
        return "Please enter a query."

    response = fetch_youtube_results(query)
    # Generate a list of embedded YouTube videos
    video_elements = []
    for title, video_id in zip(response["title"], response["video_id"]):
        video_elements.append(
            html.Div(
                children=[
                    html.H4(title),
                    html.Iframe(
                        src=f"https://www.youtube.com/embed/{video_id}",
                        width="560",
                        height="315",
                        style={"border": "none"},
                    ),
                    html.Hr(),  # Separator
                ],
                style={"margin-bottom": "20px"},
            )
        )

    return video_elements
