Contributing
============

Thank you for your interest in contributing to
Django-AWS-API-Gateway-WebSockets.

Ways to contribute
------------------

You can help by:

* reporting bugs;
* improving documentation;
* adding tests;
* fixing issues;
* proposing new features;
* reviewing pull requests.

Development setup
-----------------

Fork the repository and clone your fork locally.

Install the development requirements that match the Python and Django versions
you want to test against.

Install pre-commit hooks:

.. code-block:: console

   pre-commit install

Running tests
-------------

Run the test suite with coverage:

.. code-block:: console

   coverage erase
   python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings
   coverage combine
   coverage report

To run the tests quickly, without coverage:

.. code-block:: console

   python -m pytest tests

``tox.ini`` sets ``DJANGO_SETTINGS_MODULE`` to ``tests.settings``, so ``--ds`` is
optional. The test database is in memory, so running the tests leaves no files
behind.

Most tests call views directly. ``tests/test_routing.py`` is different: it uses
the Django test ``Client`` with CSRF checks switched on and the URLs in
``tests/urls.py``, so a request goes through the URL resolver and every
middleware class. Add a test there when a change depends on routing, CSRF, or the
admin pages. ``python -m django check`` also works against ``tests.settings``, to
run the package's system checks.

Pull requests
-------------

Before opening a pull request:

#. Check for an existing issue or open a new one.
#. Add or update tests for your change.
#. Update documentation where appropriate.
#. Run the test suite.
#. Run pre-commit checks.
#. Add yourself to ``AUTHORS`` if appropriate.
#. Open a pull request against the main repository.

Documentation changes
---------------------

Documentation is built with Sphinx.

To build the docs locally:

.. code-block:: console

   cd docs
   make html

The generated HTML will be available under ``docs/_build/html``.

Regenerating the API reference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The pages in ``docs/api/`` are generated from the Python modules with
``sphinx-apidoc``. They list the modules and pull in the docstrings with
``autodoc``, so a docstring change shows up when you build the docs. You only need
to regenerate them when a module is added, renamed or removed:

.. code-block:: console

   cd docs
   make apidoc

This needs ``sphinx`` to be installed, because it runs ``sphinx-apidoc``. It
leaves out the ``migrations`` and ``management`` folders. Check the result with
``git diff docs/api``, because a newer Sphinx can reorder the options in the files
it rewrites. Keep only the real changes, which are new module pages and the
submodule list in ``django_aws_api_gateway_websockets.rst``.

The hand-written reference pages are ``docs/views.rst``, ``docs/mixins.rst`` and
``docs/settings.rst``. Update them when you change what a view or mixin does.

Style guidelines
----------------

When contributing code:

* keep changes focused;
* prefer readable code over clever code;
* include tests for bug fixes and new functionality;
* avoid unrelated formatting changes;
* document public behaviour.