Installation
============

Install the package
-------------------

Install Django-AWS-API-Gateway-WebSockets into your Django environment.

.. code-block:: console

   pip install django-aws-api-gateway-websockets

Add the app
-----------

Add the package to ``INSTALLED_APPS`` in your Django settings.

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "django_aws_api_gateway_websockets",
   ]

Configuring settings.py
-----------------------

See * :doc:`settings`; for more information

Run migrations
--------------

Apply the database migrations.

.. code-block:: console

   python manage.py migrate

Configure Django
----------------

After installation, configure the required Django settings for your AWS account,
API Gateway setup, and WebSocket routing.

See :doc:`configuration` for details.

Configure AWS permissions
-------------------------

The application needs AWS IAM permissions to create and manage API Gateway
resources and to send messages to active WebSocket connections.

See :doc:`aws_iam_setup` for details.

Create an API Gateway record
----------------------------

Create an API Gateway configuration record using Django Admin, a management
command, or your own deployment process.

Once the record exists, you can create the API Gateway resources and custom
domain configuration if required.

Add WebSocket routes
--------------------

Add Django URL routes that receive WebSocket callbacks from AWS API Gateway.

See :doc:`adding_new_routes` for more information.
