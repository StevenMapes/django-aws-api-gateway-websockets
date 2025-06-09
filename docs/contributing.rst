============
Contributing
============

Run the tests
-------------
.. code-block::
    coverage erase && \
    python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings && \
    coverage combine && \
    coverage report

Contributing
------------
1. Check for `open issues <https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues>`__
2. Fork the `repository on GitHub <https://github.com/StevenMapes/django-aws-api-gateway-websockets>`__ to start making changes.
3. Initialise pre-commit by running `pre-commit install`
4. Install requirements from one of the requirement files depending on the versions of Python and Django you wish to use.
5. Add a test case to show that the bug is fixed or the feature is implemented correctly.
6. Test using `python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings`
7. Create a pull request, tagging the issue, bug me until I can merge your pull request. Also, don't forget to add yourself to AUTHORS.
