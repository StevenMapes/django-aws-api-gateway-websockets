Configuration
=============

Django settings
---------------

Add the application to ``INSTALLED_APPS``.

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "django_aws_api_gateway_websockets",
   ]

AWS credentials
---------------

The package uses AWS credentials to interact with API Gateway, API Gateway
Management API, ACM, and Route 53 where required.

Credentials may be provided using standard AWS mechanisms, including:

* environment variables;
* an AWS profile;
* an IAM role attached to the runtime environment;
* deployment-specific secret management.

For production deployments, prefer IAM roles or managed secrets over hard-coded
credentials.

AWS region
----------

Configure the AWS region where your API Gateway resources should be created.

Use the same region consistently for API Gateway resources and related AWS
resources unless your deployment has a specific reason to do otherwise.

API Gateway records
-------------------

The package stores API Gateway configuration in Django models.

An API Gateway record usually represents a WebSocket API Gateway endpoint and
contains the information needed to:

* identify the API Gateway;
* validate incoming requests;
* send messages back to active connections;
* manage custom domain configuration;
* associate sessions with the correct gateway.

Channels
--------

WebSocket sessions can be grouped by channel.

Channels allow your application to send messages to a subset of active
connections rather than sending every message to every connected client.

Common channel strategies include:

* one channel per application;
* one channel per user;
* one channel per tenant;
* one channel per room, document, dashboard, or resource.

Custom domains
--------------

If you use a custom domain for your WebSocket endpoint, configure the domain,
certificate, and DNS records in AWS.

The package can help create and track some of this configuration, but you should
verify the generated AWS resources before using them in production.

Security considerations
-----------------------

When configuring the package, make sure that:

* only trusted API Gateway endpoints can call your Django WebSocket views;
* AWS credentials are not committed to source control;
* IAM permissions are limited to the required actions and resources;
* stale or disconnected sessions are cleaned up regularly;
* incoming payloads are validated before being trusted.