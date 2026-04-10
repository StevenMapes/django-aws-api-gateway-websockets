# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import django

sys.path.insert(0, os.path.abspath(".."))
os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
django.setup()

from django.conf import settings  # noqa

import django_aws_api_gateway_websockets  # noqa

# -- Path setup --------------------------------------------------------------

here = Path(__file__).parent.resolve()
sys.path.insert(0, str(here / ".."))

# -- Project information -----------------------------------------------------

project = "Django-AWS-Api-Gateway-WebSockets"
copyright = "2021 Steven Mapes"
author = "Steven Mapes"

# The version info for the project you're documenting, acts as replacement
# for |version| and |release|, also used in various other places throughout
# the built documents.


def _get_version() -> str:
    with (here / ".." / "pyproject.toml").open("rb") as fp:
        data = tomllib.load(fp)
    version: str = data["project"]["version"]
    return version


version = _get_version()
release = version

# -- General configuration ---------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = [
    ".venv",
    "_build",
]

# -- Options for HTML output -------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "furo"
html_theme_options = {
    "dark_css_variables": {
        "admonition-font-size": "100%",
        "admonition-title-font-size": "100%",
    },
    "light_css_variables": {
        "admonition-font-size": "100%",
        "admonition-title-font-size": "100%",
    },
}

# The name of an image file (within the static path) to use as favicon
# of the docs.  This file should be a Windows icon file (.ico) being
# 16x16 or 32x32 pixels large.
html_favicon = "_static/favicon.ico"

# Add any paths that contain custom static files (such as style sheets)
# here, relative to this directory. They are copied after the builtin
# static files, so a file named "default.css" will overwrite the builtin
# "default.css".
html_static_path = ["_static"]

epub_exclude_files = [
    "_static/favicon.ico",
]

# -- Options for LaTeX output ------------------------------------------

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto/manual]).
latex_documents = [
    (
        "index",
        "django-aws-api-gateway-webSockets.tex",
        "Django-AWS-Api-Gateway-WebSockets Documentation",
        "Steven Mapes",
        "manual",
    ),
]

# -- Options for Intersphinx -------------------------------------------

intersphinx_mapping = {
    "django": (
        "https://docs.djangoproject.com/en/stable/",
        "https://docs.djangoproject.com/en/stable/_objects/",
    ),
}
