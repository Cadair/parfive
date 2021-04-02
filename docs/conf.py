"""
Configuration file for the Sphinx documentation builder.

isort:skip_file
"""
# flake8: NOQA: E402

# -- stdlib imports ------------------------------------------------------------
import os
import sys
import datetime
from pkg_resources import get_distribution
from packaging.version import Version

# -- Check for dependencies ----------------------------------------------------

doc_requires = get_distribution("parfive").requires(extras=("docs",))
missing_requirements = []
for requirement in doc_requires:
    try:
        get_distribution(requirement)
    except Exception as e:
        missing_requirements.append(requirement.name)
if missing_requirements:
    print(
        f"The {' '.join(missing_requirements)} package(s) could not be found and "
        "is needed to build the documentation, please install the 'docs' requirements."
    )
    sys.exit(1)

# -- Project information -------------------------------------------------------

project = 'Parfive'
author = 'Stuart Mumford and Contributors'
copyright = '{}, {}'.format(datetime.datetime.now().year, author)

# The full version, including alpha/beta/rc tags
from parfive import __version__
release = __version__
parfive_version = Version(__version__)
is_release = not(parfive_version.is_prerelease or parfive_version.is_devrelease)

# -- SunPy Sample Data and Config ----------------------------------------------


# -- General configuration -----------------------------------------------------

# Suppress warnings about overriding directives as we overload some of the
# doctest extensions.
suppress_warnings = ['app.add_directive', ]

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.coverage',
    'sphinx.ext.doctest',
    'sphinx.ext.inheritance_diagram',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
    'sphinx.ext.napoleon',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
    'sphinx_automodapi.automodapi',
    'sphinx_automodapi.smart_resolver',
    'sphinx_changelog',
]

# Add any paths that contain templates here, relative to this directory.
# templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
html_extra_path = ['robots.txt']

exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# The reST default role (used for this markup: `text`) to use for all
# documents. Set to the "smart" one.
default_role = 'obj'

# Disable having a separate return type row
napoleon_use_rtype = False

# Disable google style docstrings
napoleon_google_docstring = False

# -- Options for intersphinx extension -----------------------------------------

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {'https://docs.python.org/': None,
                       'http://aiohttp.readthedocs.io/en/stable': None,
                       'https://aioftp.readthedocs.io/': None}

# -- Options for HTML output ---------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.

from sunpy_sphinx_theme.conf import *  # NOQA

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = ['_static']

# Render inheritance diagrams in SVG
graphviz_output_format = "svg"

graphviz_dot_args = [
    '-Nfontsize=10',
    '-Nfontname=Helvetica Neue, Helvetica, Arial, sans-serif',
    '-Efontsize=10',
    '-Efontname=Helvetica Neue, Helvetica, Arial, sans-serif',
    '-Gfontsize=10',
    '-Gfontname=Helvetica Neue, Helvetica, Arial, sans-serif'
]

html_theme_options = {'logo_url': 'https://parfive.readthedocs.io/en/latest/'}
# Sidebar broke the docs.
html_sidebars.pop("**")
