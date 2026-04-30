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

Style guidelines
----------------

When contributing code:

* keep changes focused;
* prefer readable code over clever code;
* include tests for bug fixes and new functionality;
* avoid unrelated formatting changes;
* document public behaviour.