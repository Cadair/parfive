# -*- coding: utf-8 -*-
#
# Configuration file for the Sphinx documentation builder.
#
# This file does only contain a selection of the most common options. For a
# full list see the documentation:
# http://www.sphinx-doc.org/en/master/config


# -- Project information -----------------------------------------------------

project = 'Parfive'
copyright = '2020, Stuart Mumford and Contributors'
author = 'Stuart Mumford'

# The full version, including alpha/beta/rc tags
from parfive import __version__ as release  # NOQA

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.inheritance_diagram',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.doctest',
    'sphinx.ext.mathjax',
    'sphinx_automodapi.automodapi',
    'sphinx_automodapi.smart_resolver',
]

# Add any paths that contain templates here, relative to this directory.
# templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# -- Options for intersphinx extension ---------------------------------------

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {'https://docs.python.org/': None,
                       'http://aiohttp.readthedocs.io/en/stable': None,
                       'https://aioftp.readthedocs.io/': None}

# -- Options for HTML output -------------------------------------------------

try:
    from sunpy_sphinx_theme.conf import *  # NOQA
except ImportError:
    html_theme = 'alabaster'

html_theme_options = {'logo_url': 'https://parfive.readthedocs.io/en/latest/'}
