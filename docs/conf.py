"""
Configuration file for the Sphinx documentation builder.

isort:skip_file
"""

# flake8: NOQA: E402

# -- stdlib imports ------------------------------------------------------------
from parfive import __version__
import datetime
from packaging.version import Version

# -- Project information -------------------------------------------------------

project = "Parfive"
author = "Stuart Mumford and Contributors"
copyright = f"{datetime.datetime.now().year}, {author}"

# The full version, including alpha/beta/rc tags
release = __version__
parfive_version = Version(__version__)
is_release = not (parfive_version.is_prerelease or parfive_version.is_devrelease)

# -- General configuration -----------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.doctest",
    "sphinx.ext.inheritance_diagram",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",  # must be loaded after napoleon
    "sphinx_automodapi.automodapi",
    "sphinx_automodapi.smart_resolver",
    "sphinx_contributors",
]

# Add any paths that contain templates here, relative to this directory.
# templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
html_extra_path = ["robots.txt"]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
source_suffix = ".rst"

# The master toctree document.
master_doc = "index"

# The reST default role (used for this markup: `text`) to use for all
# documents. Set to the "smart" one.
default_role = "obj"

# Disable having a separate return type row
napoleon_use_rtype = False

# Disable google style docstrings
napoleon_google_docstring = False

# Type Hint Config
typehints_fully_qualified = False
typehints_use_rtype = napoleon_use_rtype
typehints_defaults = "comma"

# -- Options for intersphinx extension -----------------------------------------

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {
    "python": ("https://docs.python.org/", None),
    "aiohttp": ("https://docs.aiohttp.org/en/stable", None),
    "aioftp": ("https://aioftp.readthedocs.io/", None),
}

# -- Options for HTML output ---------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "sphinx_book_theme"

html_theme_options = {
    "home_page_in_toc": True,
    "repository_url": "https://github.com/Cadair/parfive",
    "use_repository_button": True,
    "use_issues_button": True,
    "use_download_button": False,
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["static"]
html_css_files = [
    "css/contributors.css",
]

html_js_files = [
    (
        "//gc.zgo.at/count.js",
        {"async": "async", "data-goatcounter": "https://parfive.goatcounter.com/count"},
    )
]

# Render inheritance diagrams in SVG
graphviz_output_format = "svg"

graphviz_dot_args = [
    "-Nfontsize=10",
    "-Nfontname=Helvetica Neue, Helvetica, Arial, sans-serif",
    "-Efontsize=10",
    "-Efontname=Helvetica Neue, Helvetica, Arial, sans-serif",
    "-Gfontsize=10",
    "-Gfontname=Helvetica Neue, Helvetica, Arial, sans-serif",
]
