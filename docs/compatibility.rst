Compatibility
=============

This page describes the supported Python, Django, and AWS compatibility for
Django-AWS-API-Gateway-WebSockets.

Supported Python versions
-------------------------

The project requires Python 3.10 or later.

The package metadata declares support for:

* Python 3.10;
* Python 3.11;
* Python 3.12;
* Python 3.13;
* Python 3.14;
* Python 3.15.

Python versions older than 3.10 are not supported.

Supported Django versions
-------------------------

The project requires Django 4.2 or later.

The package metadata declares support for:

* Django 4.2;
* Django 5.0;
* Django 5.1;
* Django 5.2;
* Django 6.0.
* Django 6.1.

Django versions older than 4.2 are not supported.

Recommended versions
--------------------

For new projects, use current supported Python and Django versions.

Recommended stable combinations include:

* Python 3.12 with Django 4.2, 5.1, or 5.2;
* Python 3.13 with Django 4.2, 5.1, or 5.2;
* Python 3.14 with Django 5.1, 5.2, or 6.0 where supported by your deployment
  environment.

If using pre-release Python or Django versions, test carefully before deploying
to production.

Compatibility matrix
--------------------

The following table summarises the intended test/support matrix.

.. list-table::
   :header-rows: 1

   * - Python
     - Django 4.2
     - Django 5.0
     - Django 5.1
     - Django 5.2
     - Django 6.0
     - Django 6.1
   * - 3.10
     - Supported
     - Legacy / not recommended
     - Supported
     - Supported
     - Not applicable
     - Not applicable
   * - 3.11
     - Supported
     - Legacy / not recommended
     - Supported
     - Supported
     - Not applicable
     - Not applicable
   * - 3.12
     - Supported
     - Legacy / not recommended
     - Supported
     - Supported
     - Supported
     - Supported
   * - 3.13
     - Supported
     - Legacy / not recommended
     - Supported
     - Supported
     - Supported
     - Supported
   * - 3.14
     - Not recommended
     - Not recommended
     - Supported
     - Supported
     - Supported
     - Supported
   * - 3.15
     - Not recommended
     - Not recommended
     - Not recommended
     - Supported
     - Supported
     - Supported

Django 5.0
----------

Django 5.0 is listed in package metadata for compatibility history, but newer
Django 5.x versions are recommended for active projects.

If possible, use Django 5.1 or 5.2 instead of Django 5.0.

Django 6.0
----------

Django 6.0 support depends on the Python version used by your environment.

Use a Python version supported by Django 6.0 and test your deployment carefully.

Python 3.14 and 3.15
--------------------

Python 3.14 and Python 3.15 support may depend on the maturity of your full
dependency stack.

Before using these versions in production, check compatibility for:

* Django;
* Boto3;
* Botocore;
* Sphinx, if building documentation;
* your database driver;
* your deployment platform;
* any authentication, storage, or background task packages used by your project.

AWS compatibility
-----------------

This package is designed to work with AWS API Gateway WebSocket APIs.

The AWS services involved may include:

* API Gateway V2;
* API Gateway Management API;
* AWS Certificate Manager;
* Route 53;
* CloudWatch Logs, depending on your API Gateway logging setup.

AWS credentials
---------------

The package uses Boto3 and supports standard AWS credential approaches,
including:

* IAM roles;
* named AWS profiles;
* explicit access key and secret key settings;
* environment-provided credentials.

For production deployments, IAM roles are recommended where possible.

See :doc:`aws_iam_setup` and :doc:`settings`.

Browser compatibility
---------------------

The client-side examples use the browser WebSocket API.

Modern browsers support WebSockets, including:

* Chrome;
* Firefox;
* Safari;
* Edge;
* modern mobile browsers.

For production applications, use ``wss://`` rather than ``ws://``.

Reconnect behaviour is not built into the browser WebSocket API. If you need
automatic reconnects, use a reconnecting client library or implement reconnect
logic yourself.

See :doc:`reconnecting_websocket`.

Documentation build compatibility
---------------------------------

The documentation is built with Sphinx.

The Read the Docs configuration defines the Python version used for the
published documentation build.

If building locally on Python 3.10, ensure the docs requirements include the
``tomli`` backport because ``tomllib`` is only included in the Python standard
library from Python 3.11 onward.

Install documentation dependencies with:

.. code-block:: console

   pip install -r docs/requirements.txt

Then build the docs:

.. code-block:: console

   cd docs
   make html

Package dependencies
--------------------

Core runtime dependencies include:

* Django;
* Boto3.

Boto3 brings in Botocore and related AWS dependencies.

Check your lock files or deployment environment to confirm exact dependency
versions.

Testing compatibility
---------------------

Before deploying a new Python or Django combination, run the test suite.

.. code-block:: console

   coverage erase
   python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings
   coverage combine
   coverage report

If using tox, run the relevant tox environments.

.. code-block:: console

   tox

Upgrade guidance
----------------

When changing Python or Django versions:

* read the changelog;
* run migrations;
* run the full test suite;
* test WebSocket token generation;
* test WebSocket connection and disconnection;
* test message sending;
* test API Gateway setup commands if relevant;
* test cleanup commands;
* test deployment in staging before production.

See :doc:`upgrade_guide`.

Support policy
--------------

The project aims to actively support current Python and Django versions.

Older versions may continue to work, but they are not guaranteed to be tested or
supported.

For best results, use a Python and Django combination that is actively supported
by both this project and the Django project.

Related pages
-------------

See also:

* :doc:`installation`;
* :doc:`configuration`;
* :doc:`settings`;
* :doc:`aws_iam_setup`;
* :doc:`deployment`;
* :doc:`testing`;
* :doc:`upgrade_guide`;
* :doc:`changelog`.
