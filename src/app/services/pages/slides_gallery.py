import logging

import dash
import dash_bootstrap_components as dbc
import requests
from bs4 import BeautifulSoup
from dash import Input, Output, callback, html

from app.services.utils.file_utils import card_style
from config.logging import setup_logging
from config.settings import settings

setup_logging()
logger = logging.getLogger(__name__)

if settings.env != 'testing':
    dash.register_page(__name__, path='/slides-gallery', name='Slides Gallery', order=1)

BASE_URL = 'https://pgalmiche.gitlab.io/manim-slides-factory/'


def fetch_slides():
    """Scrape the GitLab Pages index.html for slide links."""
    resp = requests.get(f'{BASE_URL}index.html')
    soup = BeautifulSoup(resp.text, 'html.parser')
    slides = [a['href'] for a in soup.select('ul li a') if a['href'].endswith('.html')]
    return slides


def build_gallery(slides):
    """Interactive Reveal.js slides in Dash with responsive iframe and download links."""
    return html.Div(
        [
            html.Div(
                [
                    # Responsive iframe for Reveal.js deck
                    html.Div(
                        html.Iframe(
                            src=f'{BASE_URL}{slide}',
                            style={
                                'position': 'absolute',
                                'top': '0',
                                'left': '0',
                                'width': '100%',
                                'height': '100%',
                                'border': 'none',
                            },
                        ),
                        style={
                            'position': 'relative',
                            'paddingBottom': '56.25%',  # 16:9 aspect ratio
                            'height': 0,
                            'overflow': 'hidden',
                            'marginBottom': '1rem',
                        },
                    ),
                    # Title below
                    html.Div(
                        slide.replace('.html', ''),
                        style={'fontWeight': 'bold', 'marginBottom': '0.5rem'},
                    ),
                    # Download buttons
                    html.Div(
                        [
                            html.A(
                                '🔗 Open Fullscreen',
                                href=f'{BASE_URL}{slide}',
                                target='_blank',
                                style={'marginRight': '1rem'},
                            ),
                            html.A(
                                '📄 PDF',
                                href=f"{BASE_URL}{slide.replace('.html', '.pdf')}",
                                target='_blank',
                                style={'marginRight': '1rem'},
                            ),
                            html.A(
                                '📊 PPTX',
                                href=f"{BASE_URL}{slide.replace('.html', '.pptx')}",
                                target='_blank',
                            ),
                        ],
                        style={'textAlign': 'center'},
                    ),
                ],
                style={
                    'width': '45%',
                    'display': 'inline-block',
                    'verticalAlign': 'top',
                    'margin': '2%',
                },
            )
            for slide in slides
        ],
        style={'textAlign': 'center'},
    )


layout = html.Div(
    [
        html.H1('Welcome to the Slides Gallery', className='fw-bold mb-3'),
        html.P(
            "Navigate various slides and don't hesitate to open in another file and press f for fullscreen."
        ),
        dbc.Button(
            '🏠 Back to Home',
            href='/',  # your home page path
            color='primary',
            className='me-2',
        ),
        html.Br(),
        html.Br(),
        dbc.Card(
            dbc.CardBody(
                [
                    html.H2(
                        children=[
                            'Slides generated with the ',
                            html.A(
                                'manim-slides-factory',
                                href='https://gitlab.com/pgalmiche/manim-slides-factory:',  # repo URL
                                target='_blank',
                                style={
                                    'textDecoration': 'underline',
                                    'color': '#0366d6',
                                },
                            ),
                            ' project:',
                        ]
                    ),
                    html.P(
                        [
                            'These slides were created using the ',
                            html.A(
                                'Manim-slides',
                                href='https://manim-slides.eertmans.be/latest/',
                                target='_blank',
                                style={
                                    'textDecoration': 'underline',
                                    'color': '#0366d6',
                                },
                            ),
                            ' Python library. Use the arrows to navigate through the presentations. ',
                            html.Br(),
                            'Click on ',
                            html.B('Open Fullscreen'),
                            ' to view the slide in a new page, or download the PDF or PPTX versions using the corresponding links below.',
                        ]
                    ),
                    html.Div(id='gallery-container'),  # Container for slide gallery
                    html.Button(
                        'Refresh Gallery',
                        id='refresh-btn',
                        n_clicks=0,
                        style={'marginBottom': '2rem'},
                    ),
                ]
            ),
            className='mb-3',
            style=card_style,
        ),
        html.Br(),
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(
                        [
                            html.H2('Slides manually added from other sources:'),
                            html.P(
                                'To run the presentation, click on Open Slide and press f for full screen.'
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                'Defense Presentation',
                                                style={
                                                    'fontWeight': 'bold',
                                                    'marginBottom': '0.5rem',
                                                },
                                            ),
                                            html.Div(
                                                html.Iframe(
                                                    src='https://pgalmiche.gitlab.io/defense-presentation',
                                                    style={
                                                        'position': 'absolute',
                                                        'top': '0',
                                                        'left': '0',
                                                        'width': '100%',
                                                        'height': '100%',
                                                        'border': 'none',
                                                    },
                                                ),
                                                style={
                                                    'position': 'relative',
                                                    'paddingBottom': '56.25%',  # 16:9 aspect ratio
                                                    'height': 0,
                                                    'overflow': 'hidden',
                                                    'marginBottom': '1rem',
                                                },
                                            ),
                                            # Link to open the slide online
                                            html.Div(
                                                [
                                                    html.A(
                                                        '🔗 Open Slide',
                                                        href='https://pgalmiche.gitlab.io/defense-presentation',
                                                        target='_blank',
                                                        style={'marginRight': '1rem'},
                                                    ),
                                                ],
                                                style={'textAlign': 'center'},
                                            ),
                                        ],
                                        style={
                                            'width': '45%',
                                            'display': 'inline-block',
                                            'verticalAlign': 'top',
                                            'margin': '2%',
                                        },
                                    )
                                ]
                            ),
                        ]
                    ),
                ]
            ),
            className='mb-3',
            style=card_style,
        ),
    ]
)


@callback(Output('gallery-container', 'children'), Input('refresh-btn', 'n_clicks'))
def update_gallery(n_clicks):
    slides = fetch_slides()
    return build_gallery(slides)
