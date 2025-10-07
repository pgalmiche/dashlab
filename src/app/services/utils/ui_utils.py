"""
This module is used to centralize utilities for the user interface.

Features:
- Create cards for the projects in PROJECT_RULES with badges showing if user has access or not.

Dependencies:
- Dash for the html outputs

Usage:
Import from pages to quickly set up working UI for various projects, with display and management of files.
"""

import os

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services.utils.file_utils import (
    generate_presigned_url,
    get_thumbnail_key,
    is_audio,
    is_image,
    is_pdf,
    is_video,
    thumbnail_exists,
)

card_style = {
    'backgroundColor': '#e9f5ff',  # custom light blue
    'color': '#333333',  # text color
    'borderRadius': '12px',
    'boxShadow': '0 4px 12px rgba(0, 0, 0, 0.08)',
    'padding': '20px',
    'marginBottom': '20px',
}

bucket_attribute_map = {
    'splitbox-bucket': 'custom:splitbox-access',
    'personnal-files-pg': 'custom:personnal-files-pg',
    'dashlab-bucket': 'custom:dashlab',
    'galmiche-family': 'custom:galmiche-family',
    'pgvv': 'custom:pgvv',
    'splitbox-contributor': 'custom:splitbox-contributor',
}

# Centralized project definitions
PROJECT_RULES = {
    'slides': {
        'title': ' 🎞️Slides Gallery',
        'description': 'Browse and interact with nice presentations.',
        'attr': None,  # No restriction
        'href': '/slides-gallery',
        'requires_auth': False,
    },
    'gallery': {
        'title': '📸 Gallery',
        'description': 'Browse the various files in your buckets.',
        'attr': None,  # No restriction
        'href': '/gallery',
        'requires_auth': False,
    },
    'splitbox': {
        'title': '🎵 SplitBox',
        'description': 'Upload/Record audio files and analyze them automatically.',
        'attr': 'custom:splitbox-access',  # Requires attribute
        'href': '/splitbox',
        'requires_auth': True,
    },
}


def get_project_status(user, project_key):
    """
    Returns (label_text, label_color, is_enabled) for a given project.
    """
    rules = PROJECT_RULES.get(project_key)
    if not rules:
        return 'Need authorization', 'warning', False

    # If project is public → always allow
    if not rules.get('requires_auth', True):
        return 'Always available', 'secondary', True

    # If user is not logged in → no access
    if not user:
        return 'Need authorization', 'warning', False

    # Check attribute
    value = user.get(rules['attr'], 'false').lower()
    if value == 'true':
        return 'Access granted', 'success', True
    else:
        return 'Need authorization', 'warning', False


def build_project_cards(user):
    """
    Return a list of dbc.Col cards for all projects.
    """
    cards = []
    for key, project in PROJECT_RULES.items():
        status_text, status_color, enabled = get_project_status(user, key)

        card = dbc.Col(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.H5(
                                [
                                    project['title'],
                                    dbc.Badge(
                                        status_text,
                                        color=status_color,
                                        className='ms-2',
                                    ),
                                ],
                                className='card-title',
                            ),
                            html.P(project['description'], className='card-text'),
                            dbc.Button(
                                'Go',
                                href=project['href'],
                                color='primary',
                                className='mt-2',
                                # disabled=not enabled,
                            ),
                        ]
                    )
                ],
                className='mb-4 shadow-sm',
                style={'minHeight': '160px'},
            ),
            md=6,
        )
        cards.append(card)
    return cards


def build_project_section(user):
    """
    Wrap cards with a short explanation text.
    """
    return html.Div(
        [
            html.P(
                [
                    '🔒 Projects with a ',
                    html.Span('Need authorization', style={'color': '#856404'}),
                    ' badge require special access, but you still can go to the demo! ',
                    html.Br(),
                    html.Span('Access granted', style={'color': '#155724'}),
                    ' means you are authorized. ',
                    html.Br(),
                    html.Span('Always available', style={'color': '#6c757d'}),
                    ' means anyone can use it.',
                ],
                style={'marginTop': '1rem'},
            ),
            dbc.Row(build_project_cards(user)),
        ]
    )


def bucket_dropdown(layout_id: str):
    """Create a responsive dropdown component for S3 buckets."""
    return html.Div(
        id=layout_id,
        style={'width': '100%', 'maxWidth': '400px'},  # responsive width
        children=[
            dcc.Dropdown(
                id=layout_id,
                options=[],  # will be populated dynamically via callback
                value=None,
                clearable=False,
                style={'width': '100%'},  # take full parent width
            )
        ],
    )


def render_file_preview(
    s3_client,
    bucket_name: str,
    file_key: str,
    show_download: bool = True,
    show_delete: bool = False,
    allow_rename: bool = True,
    fullscreen: bool = False,
    folder_options=None,
):

    # --- Determine thumbnail ---
    preview_key = file_key
    if is_image(file_key):
        thumbnail_key = get_thumbnail_key(file_key)
        if thumbnail_exists(s3_client, bucket_name, thumbnail_key):
            preview_key = thumbnail_key

    preview_url = generate_presigned_url(s3_client, bucket_name, preview_key)
    original_url = generate_presigned_url(s3_client, bucket_name, file_key)

    # --- Main preview component ---
    if is_image(file_key):
        main_component = html.Div(
            html.Img(
                src=preview_url,
                style={
                    'maxWidth': '100%',
                    'maxHeight': '100%',
                    'objectFit': 'contain',
                    'borderRadius': '6px',
                },
            ),
            style={
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'width': '100%',
                'height': 'auto',
            },
        )
    elif is_pdf(file_key):
        main_component = html.Iframe(
            src=preview_url,
            style={
                'width': '100%',
                'height': '80vh',
                'borderRadius': '6px',
                'border': '1px solid #ddd',
            },
        )
    elif is_audio(file_key):
        main_component = html.Audio(
            src=preview_url, controls=True, style={'width': '100%'}
        )
    elif is_video(file_key):
        main_component = html.Video(
            src=preview_url,
            controls=True,
            style={'width': '100%', 'maxHeight': '80vh', 'borderRadius': '6px'},
        )
    elif file_key.endswith('_viz.json'):
        safe_id = f"viz-{file_key.replace('/', '-')}"
        main_component = html.Div(
            [
                dcc.Store(
                    id={'type': 'viz-json-store', 'file_key': file_key},
                    data=preview_url,
                ),
                html.Div(id=safe_id, style={'width': '100%', 'height': '400px'}),
            ]
        )
    else:
        main_component = html.Div(
            'Preview not available',
            style={
                'padding': '20px',
                'backgroundColor': '#f8f9fa',
                'textAlign': 'center',
                'borderRadius': '6px',
            },
        )

    # --- Buttons row (centered, uniform, small) ---
    buttons_row_children = []

    if show_download:
        buttons_row_children.append(
            dbc.Col(
                dbc.Button(
                    '⬇',
                    href=original_url,
                    target='_blank',
                    color='success',
                    size='sm',
                    className='w-100',
                ),
                width='auto',
            )
        )
    if show_delete:
        buttons_row_children.append(
            dbc.Col(
                dbc.Button(
                    '❌',
                    id={'type': 'delete-file-btn', 'file_key': file_key},
                    n_clicks=0,
                    color='danger',
                    size='sm',
                    className='w-100',
                ),
                width='auto',
            )
        )

    buttons_row_children.append(
        dbc.Col(
            dbc.Button(
                '⛶' if not fullscreen else '✖ Close',
                id={
                    'type': (
                        'toggle-fullscreen-btn'
                        if not fullscreen
                        else 'close-fullscreen-btn'
                    ),
                    'file_key': file_key,
                },
                n_clicks=0,
                color='secondary',
                size='sm',
                className='w-100',
            ),
            width='auto',
        )
    )

    buttons_row_children.append(
        dbc.Col(
            dbc.Button(
                '✏',
                id={'type': 'show-rename-btn', 'file_key': file_key},
                n_clicks=0,
                color='primary',
                size='sm',
                className='w-100',
                style={'display': 'none'} if fullscreen else {},
            ),
            width='auto',
        )
    )

    buttons_row = dbc.Row(
        buttons_row_children, className='g-2 justify-content-center mt-2'
    )

    # --- Rename section (always rendered, empty if disallowed) ---
    rename_section_children = []
    if allow_rename:
        rename_section_children = [
            dbc.Row(
                dbc.Col(
                    dcc.Input(
                        id={'type': 'rename-file-input', 'file_key': file_key},
                        type='text',
                        placeholder='New name (keep extension)',
                        style={'width': '100%', 'marginBottom': '5px'},
                    ),
                    width=12,
                ),
                className='mb-2',
            ),
            dbc.Row(
                dbc.Col(
                    dcc.Dropdown(
                        id={'type': 'move-folder-input', 'file_key': file_key},
                        options=folder_options or [],
                        placeholder='Target folder (optional)',
                        clearable=True,
                        style={'width': '100%', 'marginBottom': '5px'},
                    ),
                    width=12,
                ),
                className='mb-2',
            ),
            dbc.Row(
                dbc.Col(
                    dbc.Button(
                        '💾 Save',
                        id={'type': 'rename-file-btn', 'file_key': file_key},
                        n_clicks=0,
                        color='warning',
                        size='sm',
                        style={'width': '100%'},
                    ),
                    width=12,
                )
            ),
        ]

    rename_section = html.Div(
        id={'type': 'rename-section', 'file_key': file_key},
        style={'display': 'none', 'marginTop': '10px'},
        children=rename_section_children,
    )

    # --- Container styling ---
    container_style = {
        'margin': '10px 0',
        'padding': '10px',
        'border': '1px solid #ddd',
        'borderRadius': '8px',
        'backgroundColor': '#ffffff',
        'width': '100%',
        'maxWidth': '100%',
    }
    if fullscreen:
        container_style.update(
            {
                'position': 'fixed',
                'top': 0,
                'left': 0,
                'width': '100%',
                'height': '100%',
                'zIndex': 9999,
                'display': 'flex',
                'flexDirection': 'column',
                'alignItems': 'center',
                'justifyContent': 'center',
                'overflow': 'auto',
                'padding': '20px',
            }
        )

    # --- Assemble layout ---
    components = [main_component, buttons_row, rename_section]

    filename = os.path.basename(file_key)
    foldername = os.path.dirname(file_key) or 'Root'
    components.append(
        html.Div(
            [
                html.Div(
                    f'📁 Folder: {foldername}',
                    style={
                        'fontWeight': '600',
                        'fontSize': '12px',
                        'marginTop': '8px',
                        'whiteSpace': 'nowrap',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'width': '100%',
                        'textAlign': 'center',
                    },
                    title=foldername,
                ),
                html.Div(
                    f'🗂️ File: {filename}',
                    style={
                        'fontWeight': 'bold',
                        'fontSize': '13px',
                        'marginTop': '3px',
                        'whiteSpace': 'nowrap',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                        'width': '100%',
                        'textAlign': 'center',
                    },
                    title=filename,
                ),
            ]
        )
    )

    return html.Div(components, style=container_style), '', '', ''


def build_gallery_layout(
    s3_client,
    bucket_name: str,
    file_keys: list[str],
    show_download=True,
    show_delete=False,
    allow_rename=True,
    folder_options=None,
) -> html.Div:

    gallery_items = []

    for key in file_keys:
        display_component, tags_str, folder_name, _ = render_file_preview(
            s3_client,
            bucket_name,
            key,
            show_delete=show_delete,
            show_download=show_download,
            allow_rename=allow_rename,
            folder_options=folder_options,
        )

        preview_box = html.Div(
            display_component,
            style={
                'display': 'flex',
                'alignItems': 'center',  # vertical centering if preview_box is taller than content
                'justifyContent': 'center',  # horizontal centering
                'maxWidth': '100%',
                'overflow': 'visible',  # avoid cropping
                # remove minHeight → let tall images expand naturally
            },
        )

        item_div = html.Div(
            [
                preview_box,
                html.Div(
                    tags_str,
                    style={
                        'alignSelf': 'center',
                        'maxWidth': '100%',
                        'fontStyle': 'italic',
                        'fontSize': '12px',
                        'textAlign': 'center',
                        'marginTop': '8px',
                    },
                ),
            ],
            style={
                'border': '1px solid #ddd',
                'borderRadius': '8px',
                'padding': '15px',
                'boxSizing': 'border-box',
                'backgroundColor': '#fafafa',
                'boxShadow': '2px 2px 5px rgba(0,0,0,0.1)',
                'display': 'flex',
                'flexDirection': 'column',
                'alignItems': 'center',
                'justifyContent': 'center',  # vertical centering of stacked children
                'flex': '1 1 100%',
                'maxWidth': '320px',
                'minWidth': '240px',
            },
        )

        gallery_items.append(item_div)

    return html.Div(
        gallery_items,
        style={
            'display': 'flex',
            'flexWrap': 'wrap',
            'gap': '20px',
            'justifyContent': 'center',
            'width': '100%',
        },
    )
