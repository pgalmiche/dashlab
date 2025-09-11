"""
This module is used to centralize utilities for the user interface.

Features:
- Create cards for the projects in PROJECT_RULES with badges showing if user has access or not.

Dependencies:
- Dash for the html outputs

Usage:
Import from pages to quickly set up working UI for various projects, with display and management of files.
"""

import dash_bootstrap_components as dbc
from dash import html

# Centralized project definitions
PROJECT_RULES = {
    'slides': {
        'title': '📑 Slides Gallery',
        'description': 'Browse and interact with generated presentations.',
        'attr': None,  # No restriction
        'href': '/slides-gallery',
        'requires_auth': False,
    },
    'splitbox': {
        'title': '🎵 SplitBox',
        'description': 'Upload audio files and split them automatically.',
        'attr': 'custom:splitbox-access',  # Requires attribute
        'href': '/splitbox',
        'requires_auth': True,
    },
    'file_explorer': {
        'title': '📂 File Explorer',
        'description': 'Upload, view and manage files in S3 buckets.',
        'attr': 'custom:approved',  # Requires attribute
        'href': '/file-explorer',
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
