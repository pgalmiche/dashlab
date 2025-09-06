# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

import sys
from os import getenv
from os.path import abspath

image_tag = getenv('IMAGE_TAG', 'unknown')

rst_prolog = f"""
.. |image_tag| replace:: {image_tag}
"""

sys.path.insert(0, abspath('../../src/'))
sys.path.insert(0, abspath('.'))

# -- Project information -----------------------------------------------------

project = 'DashLab'
copyright = 'Pierre Galmiche, 2025'
author = 'Pierre Galmiche'

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.autosummary',
    'sphinx.ext.viewcode',
    'sphinx.ext.extlinks',
    'sphinx_tabs.tabs',
]

autosummary_generate = True
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
    'inherited-members': True,
}

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}

# Add any paths that contain templates here, relative to this directory.
# templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', './tests']

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'sphinx_material'
html_sidebars = {
    '**': ['logo-text.html', 'globaltoc.html', 'localtoc.html', 'searchbox.html']
}
# Material theme options (see theme.conf for more information)
html_theme_options = {
    # Set the name of the project to appear in the navigation.
    'nav_title': 'DashLab - A UI for cool projects.',
    # Set you GA account ID to enable tracking
    # "google_analytics_account": "UA-XXXXX",
    # Specify a base_url used to generate sitemap.xml. If not
    # specified, then no sitemap will be built.
    # "base_url": "https://project.github.io/project",
    # Set the color and the accent color
    'color_primary': 'blue',
    'color_accent': 'light-blue',
    # Set the repo location to get a badge with stats
    'repo_url': 'https://gitlab.com/pgalmiche/dashlab',
    'repo_name': 'DashLab',
    # Visible levels of the global TOC; -1 means unlimited
    'globaltoc_depth': 2,
    # If False, expand all TOC entries
    'globaltoc_collapse': False,
    # If True, show hidden TOC entries
    'globaltoc_includehidden': True,
    'html_minify': True,
    'css_minify': True,
    'logo_icon': '&#xea4b;',
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
# html_css_files = ["theme.css"]
master_doc = 'index'

extlinks = {
    'K3D': ('http://www.k3d-jupyter.org/%s', '%s'),
    'Numpy': ('https://numpy.org/%s', '%s'),
    'Vedo': ('https://vedo.embl.es/%s', '%s'),
    'Colour': ('https://github.com/vaab/colour/%s', '%s'),
    'SimExporter': ('https://github.com/RobinEnjalbert/SimExporter/%s', '%s'),
    'Docker': ('https://www.docker.com/%s', '%s'),
}

autodoc_mock_imports = ['vtk', 'vedo']
