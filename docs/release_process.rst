Release process
===============

This page describes the recommended release process for maintainers of
Django-AWS-API-Gateway-WebSockets.

It is intended for project maintainers rather than end users.

Overview
--------

A release usually involves:

#. reviewing open changes;
#. updating the version;
#. updating the changelog;
#. running tests;
#. building the package;
#. checking the package contents;
#. publishing to PyPI;
#. creating a Git tag or GitHub release;
#. confirming that Read the Docs has rebuilt.

Before starting
---------------

Before preparing a release, check that:

* the main branch is green in CI;
* all intended pull requests have been merged;
* documentation has been updated;
* new public behaviour is covered by tests;
* the changelog has been updated;
* dependency updates are intentional;
* the package builds successfully.

Check the current version
-------------------------

The package version is defined in ``pyproject.toml``.

Check the current version before deciding the next one.

Use semantic versioning
-----------------------

Use semantic versioning where practical:

``MAJOR``
   Breaking changes.

``MINOR``
   New backwards-compatible functionality.

``PATCH``
   Backwards-compatible bug fixes.

Examples:

.. code-block:: text

   1.4.1 -> 1.4.2   bug fix
   1.4.1 -> 1.5.0   new feature
   1.4.1 -> 2.0.0   breaking change

Update the version
------------------

Update the version in ``pyproject.toml``.

Example:

.. code-block:: toml

   [project]
   version = "1.5.0"

If the version is referenced anywhere else in the project, update those
references too.

Update the changelog
--------------------

Update ``docs/changelog.rst`` with the new release notes.

A typical entry should include:

* version number;
* release date;
* added features;
* bug fixes;
* documentation changes;
* deprecations;
* removals;
* security-related changes, where appropriate.

Example:

.. code-block:: rst

   1.5.0 - 30th April 2026
   =======================

   - Added WebSocket token documentation.
   - Added deployment and troubleshooting guides.
   - Improved API Gateway setup documentation.

If the project adopts Towncrier or another changelog tool, generate the
changelog before building the release.

Example Towncrier workflow:

.. code-block:: console

   towncrier build --version 1.5.0

Review generated changes before committing them.

Run formatting and pre-commit checks
------------------------------------

Run pre-commit checks before release.

.. code-block:: console

   pre-commit run --all-files

If pre-commit updates files, review and commit the changes.

Run tests
---------

Run the test suite.

.. code-block:: console

   coverage erase
   python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings
   coverage combine
   coverage report

If the project uses tox for the full compatibility matrix, run tox before
publishing.

.. code-block:: console

   tox

At minimum, make sure CI has passed for the supported Python and Django
combinations.

Build the documentation locally
-------------------------------

Build the Sphinx documentation locally.

.. code-block:: console

   cd docs
   make html

Open the generated HTML and check:

* the index page renders correctly;
* new pages are included in the toctree;
* cross-references work;
* code blocks render correctly;
* there are no unexpected warnings;
* the changelog is visible.

Build the package
-----------------

Build the source distribution and wheel.

.. code-block:: console

   python -m build --sdist --wheel

This creates files under:

.. code-block:: text

   dist/

If the ``build`` package is not installed in your release environment, install it
into your virtual environment first.

.. code-block:: console

   python -m pip install build

Check the package
-----------------

Use Twine to check the built distributions.

.. code-block:: console

   python -m twine check dist/*

If Twine is not installed, install it into your virtual environment.

.. code-block:: console

   python -m pip install twine

Inspect the package contents
----------------------------

Before uploading, inspect the generated files.

Useful checks include:

* package modules are included;
* migrations are included;
* management commands are included;
* license file is included;
* README is included;
* metadata is correct;
* version is correct.

You can inspect the source distribution manually by unpacking it from ``dist/``.

Test publish if needed
----------------------

For larger releases, consider uploading to TestPyPI first.

.. code-block:: console

   python -m twine upload --repository testpypi dist/*

Then install from TestPyPI in a clean virtual environment and perform a smoke
test.

.. code-block:: console

   python -m pip install --index-url https://test.pypi.org/simple/ django-aws-api-gateway-websockets

Publishing to PyPI
------------------

When ready, upload to PyPI.

.. code-block:: console

   python -m twine upload dist/*

Use a PyPI API token rather than a password.

Do not commit PyPI tokens to the repository.

Create a Git commit
-------------------

Commit the release changes.

.. code-block:: console

   git add pyproject.toml docs/changelog.rst
   git commit -m "Release 1.5.0"

Include any other files that were intentionally changed as part of the release.

Create a Git tag
----------------

Create an annotated tag for the release.

.. code-block:: console

   git tag -a 1.5.0 -m "Release 1.5.0"

Push the commit and tag.

.. code-block:: console

   git push origin main
   git push origin 1.5.0

If your project uses a ``v`` prefix for tags, use that consistently instead.

Example:

.. code-block:: console

   git tag -a v1.5.0 -m "Release 1.5.0"
   git push origin v1.5.0

Create a GitHub release
-----------------------

Create a GitHub release from the tag.

The release notes can usually be copied from ``docs/changelog.rst``.

Include:

* summary of the release;
* notable features;
* bug fixes;
* breaking changes;
* upgrade notes;
* links to documentation.

Confirm Read the Docs build
---------------------------

After pushing to ``main`` or creating a release, confirm that Read the Docs has
rebuilt successfully.

Check:

* the build completed;
* the new changelog is visible;
* the version shown in the docs is correct;
* new pages render as expected.

If GitHub Actions triggers the Read the Docs build, check the workflow result as
well.

Post-release checks
-------------------

After publishing, perform a quick smoke test.

In a clean virtual environment:

.. code-block:: console

   python -m pip install django-aws-api-gateway-websockets

Then check:

* the package imports;
* Django can include the app in ``INSTALLED_APPS``;
* migrations are available;
* management commands are available;
* documentation links work;
* PyPI shows the correct version.

Start the next development cycle
--------------------------------

After the release, decide whether to update the version to the next development
version.

For example:

.. code-block:: toml

   [project]
   version = "1.5.1.dev0"

Only do this if that matches the project's versioning approach.

Release checklist
-----------------

Use this checklist for each release.

Pre-release
~~~~~~~~~~~

* Main branch is up to date.
* CI is passing.
* Version has been updated.
* Changelog has been updated.
* Documentation has been updated.
* Tests have been run.
* Pre-commit checks pass.
* Documentation builds locally.

Build
~~~~~

* Old build artifacts have been removed.
* Source distribution has been built.
* Wheel has been built.
* Twine check passes.
* Package contents have been inspected.

Publish
~~~~~~~

* Package has been uploaded to PyPI.
* Git commit has been created.
* Git tag has been created.
* Commit and tag have been pushed.
* GitHub release has been created.
* Read the Docs build has completed.

Post-release
~~~~~~~~~~~~

* Package installs from PyPI.
* Version on PyPI is correct.
* Documentation version is correct.
* Changelog is visible.
* Any release announcement has been made.

Cleaning old build artifacts
----------------------------

Before building, remove old artifacts.

.. code-block:: console

   rm -rf dist build *.egg-info

On Windows PowerShell:

.. code-block:: powershell

   Remove-Item -Recurse -Force dist, build, *.egg-info

Common release problems
-----------------------

PyPI rejects the upload
~~~~~~~~~~~~~~~~~~~~~~~

Possible causes:

* the version already exists on PyPI;
* the API token is invalid;
* the package metadata is invalid;
* the distribution files are malformed.

PyPI does not allow replacing an existing published version. If a version was
uploaded incorrectly, publish a new version.

Documentation does not update
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* Read the Docs build status;
* GitHub Actions workflow status;
* ``.readthedocs.yml`` configuration;
* Sphinx build warnings or errors;
* whether the relevant branch or tag is active in Read the Docs.

Package is missing files
~~~~~~~~~~~~~~~~~~~~~~~~

Check package configuration and manifest settings.

Verify that important files are included in the source distribution and wheel.

Common missing files include:

* migrations;
* management commands;
* templates;
* static files;
* license;
* README.

Version mismatch
~~~~~~~~~~~~~~~~

Check that the version in ``pyproject.toml`` matches the intended release.

If documentation reads the package version from project metadata, rebuild the
documentation after updating the version.

Related pages
-------------

See also:

* :doc:`contributing`;
* :doc:`changelog`;
* :doc:`deployment`;
* :doc:`troubleshooting`;
* :doc:`license`.
