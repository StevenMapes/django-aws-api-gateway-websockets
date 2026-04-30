Deployment
==========

This guide covers production deployment considerations for
Django-AWS-API-Gateway-WebSockets.

It assumes you already understand the basic setup flow described in
:doc:`quickstart` and :doc:`api_gateway_setup`.

Deployment overview
-------------------

A production deployment usually includes:

* a Django application reachable over HTTPS;
* AWS API Gateway WebSocket API;
* a deployed API Gateway stage;
* an optional custom WebSocket domain;
* DNS pointing to the API Gateway domain;
* AWS credentials or IAM role access;
* WebSocket token protection for authenticated connections;
* scheduled cleanup tasks;
* logging and monitoring.

Typical architecture
--------------------

A common production architecture is:

.. code-block:: text

   Browser
      |
      | wss://ws.example.com
      v
   AWS API Gateway WebSocket API
      |
      | HTTPS callback requests
      v
   Django application
      |
      | database records
      v
   WebSocketSession / WebSocketToken / ConnectionRateLimit tables

Django does not keep the WebSocket connection open itself. AWS API Gateway does
that. Django receives HTTP requests from API Gateway and sends messages back
through the API Gateway Management API.

Production checklist
--------------------

Before going live, review the following checklist.

Django
~~~~~~

* ``DEBUG`` is disabled.
* ``ALLOWED_HOSTS`` includes the required hosts.
* HTTPS is enabled.
* Session settings are correct.
* CSRF settings are correct.
* Static and media files are served correctly by your normal deployment setup.
* Logging is configured.
* Database migrations have been applied.

AWS
~~~

* API Gateway has been created.
* API Gateway stage has been deployed.
* Custom domain is configured if required.
* Certificate is valid.
* DNS points to the correct API Gateway domain.
* IAM permissions are restricted.
* AWS region is configured correctly.
* Production and non-production resources are separated.

WebSocket package
~~~~~~~~~~~~~~~~~

* API Gateway records exist in Django.
* WebSocket URL routes include ``<slug:route>``.
* WebSocket token protection is enabled for authenticated endpoints.
* Rate limiting is enabled.
* Handler whitelisting is configured where appropriate.
* Django permissions are configured where appropriate.
* Cleanup commands are scheduled.
* Stale sessions are monitored.

Django settings
---------------

Allowed hosts
~~~~~~~~~~~~~

Configure ``ALLOWED_HOSTS`` for your production domains.

Example:

.. code-block:: python

   ALLOWED_HOSTS = [
       "www.example.com",
       "example.com",
   ]

Your WebSocket custom domain is handled by API Gateway, but API Gateway forwards
requests to your Django target endpoint. Make sure the host used for the Django
target endpoint is allowed.

CSRF trusted origins
~~~~~~~~~~~~~~~~~~~~

If your application requests WebSocket tokens from a browser page, configure
CSRF trusted origins for your HTTPS site.

Example:

.. code-block:: python

   CSRF_TRUSTED_ORIGINS = [
       "https://www.example.com",
   ]

If you use separate subdomains, include the origins needed by your deployment.

Session and CSRF cookies
~~~~~~~~~~~~~~~~~~~~~~~~

If your main site and WebSocket endpoint use related subdomains, review cookie
settings carefully.

Example:

.. code-block:: text

   https://www.example.com
   wss://ws.example.com

You may need settings similar to:

.. code-block:: python

   CSRF_COOKIE_SAMESITE = "Lax"
   CSRF_COOKIE_DOMAIN = ".example.com"

   SESSION_COOKIE_SAMESITE = "Lax"
   SESSION_COOKIE_DOMAIN = ".example.com"

Be careful not to scope cookies more broadly than required.

If you change session cookie names or domains, clear old sessions where
appropriate.

Secure cookies
~~~~~~~~~~~~~~

For HTTPS production deployments, use secure cookies.

.. code-block:: python

   CSRF_COOKIE_SECURE = True
   SESSION_COOKIE_SECURE = True

AWS region
~~~~~~~~~~

Configure the AWS region used by the package.

.. code-block:: python

   AWS_GATEWAY_REGION_NAME = "eu-west-1"

If you use a named AWS profile locally, make sure production uses the intended
credential method.

AWS credentials
---------------

The package uses AWS credentials to create API Gateway resources and to send
messages to connected WebSocket clients.

For production, prefer IAM roles over long-lived access keys.

Recommended options
~~~~~~~~~~~~~~~~~~~

Use one of the following:

* an IAM role attached to the runtime environment;
* a task role for containerized deployments;
* a role assumed by the deployment process;
* a securely managed IAM user only where roles are not available.

Avoid:

* committing AWS keys to source control;
* placing AWS keys directly in settings files;
* using administrator permissions in production;
* sharing credentials between environments.

Separate deployment and runtime permissions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Consider using separate identities for deployment and runtime.

Deployment permissions may include:

* creating API Gateway APIs;
* creating routes;
* creating integrations;
* deploying stages;
* creating custom domains;
* creating API mappings;
* reading ACM certificates;
* updating DNS where applicable.

Runtime permissions usually only need to send messages to connected clients
through the API Gateway Management API.

See :doc:`aws_iam_setup`.

API Gateway deployment
----------------------

Create the API Gateway
~~~~~~~~~~~~~~~~~~~~~~

Create an API Gateway record in Django and then create the AWS resources.

Using Django Admin:

#. create the API Gateway record;
#. select the record;
#. run the ``Create API Gateway`` action.

Using a management command:

.. code-block:: console

   python manage.py createApiGateway --pk=1

Replace ``1`` with the primary key of your API Gateway record.

Deploying changes
~~~~~~~~~~~~~~~~~

When routes or integrations change, make sure the API Gateway stage is deployed.

If an additional route is created after the parent API Gateway has already been
deployed, the package can deploy the new route automatically depending on how the
route is created.

If messages are not reaching a new route, check that the stage has been
redeployed.

Custom domains
---------------

A custom domain is recommended for production.

Example:

.. code-block:: text

   wss://ws.example.com

Before creating the custom domain, make sure:

* the certificate exists in AWS Certificate Manager;
* the certificate covers the WebSocket domain;
* the certificate is validated;
* the certificate ARN is stored on the API Gateway record;
* the domain name is configured on the API Gateway record;
* the hosted zone ID is configured if using Route 53 automation.

Create the custom domain using Django Admin or the management command.

.. code-block:: console

   python manage.py createCustomDomain --pk=1

After creation, configure DNS to point your WebSocket domain to the API Gateway
domain name.

DNS
---

If using a custom WebSocket domain, create the required DNS record.

For example:

.. code-block:: text

   ws.example.com

should point to the API Gateway domain name shown on the API Gateway record.

If DNS is managed outside Route 53, create the record with your DNS provider.

After changing DNS, allow time for propagation.

WebSocket tokens in production
------------------------------

For authenticated WebSocket connections, keep WebSocket token protection enabled.

Recommended production behaviour:

* user loads an authenticated Django page;
* browser requests a token from the token endpoint;
* browser immediately opens a WebSocket connection with the token;
* token is consumed during connection;
* reconnects request a fresh token.

Example connection URL:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Do not reuse tokens.

See :doc:`websocket_tokens`.

Rate limiting
-------------

Keep rate limiting enabled in production.

The default connection rate limit is:

.. code-block:: text

   20 connection attempts per 5 minutes

You can adjust this per view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 20
       RATE_LIMIT_WINDOW_MINUTES = 5

       def default(self, request, *args, **kwargs):
           return None

If legitimate users are rate limited, review both:

* server-side limits;
* frontend reconnect behaviour.

See :doc:`rate_limiting`.

Permissions
-----------

Use Django permissions for WebSocket features that should not be available to
all authenticated users.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class StaffNotificationsWebSocketView(WebSocketView):
       permissions_required = [
           "staff.can_receive_notifications",
       ]

       def default(self, request, *args, **kwargs):
           return None

For object-level access, validate inside the handler.

Examples:

* user can join this room;
* user can view this project;
* user belongs to this tenant;
* user may send to this channel.

See :doc:`permissions`.

Client reconnect strategy
-------------------------

Production clients should expect WebSocket connections to close.

Use a reconnecting strategy with backoff.

If WebSocket tokens are enabled, every new connection attempt must request a new
token.

Do not reconnect in a tight loop. Rapid reconnect attempts can trigger rate
limits and increase load.

See :doc:`reconnecting_websocket`.

Scheduled cleanup
-----------------

Schedule cleanup tasks in production.

Recommended cleanup tasks include:

* clearing old disconnected WebSocket sessions;
* deleting expired or used WebSocket tokens;
* deleting old rate limit records.

Example commands:

.. code-block:: console

   python manage.py clearWebSocketSessions
   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

Example cron schedule:

.. code-block:: text

   */5 * * * * cd /path/to/project && /path/to/venv/bin/python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

Choose the scheduling mechanism that fits your platform:

* cron;
* systemd timers;
* Celery Beat;
* Kubernetes CronJobs;
* ECS scheduled tasks;
* Heroku Scheduler;
* platform-specific scheduled jobs.

See :doc:`cleanup`.

Logging and monitoring
----------------------

Monitor both Django and AWS API Gateway.

Useful Django signals to monitor include:

* rejected connection attempts;
* rate limit rejections;
* token validation failures;
* permission denials;
* invalid channel names;
* message send failures;
* stale session counts;
* cleanup command output.

Useful AWS signals include:

* API Gateway connection errors;
* API Gateway integration errors;
* custom domain errors;
* stage deployment issues;
* throttling;
* 4xx and 5xx responses.

Also monitor frontend errors, especially:

* WebSocket connection failures;
* reconnect loops;
* token request failures;
* JSON parsing errors;
* unexpected close events.

Database considerations
-----------------------

The package stores records for:

* API Gateway configuration;
* WebSocket sessions;
* WebSocket tokens;
* connection rate limit attempts;
* additional routes.

In production:

* run migrations before deploying code that depends on new models;
* schedule cleanup for high-churn tables;
* monitor table growth;
* index application-specific models used by WebSocket handlers;
* avoid heavy synchronous work inside WebSocket handlers.

If a handler needs to start an expensive operation, consider sending a small
acknowledgement over WebSocket and processing the work asynchronously.

Environment separation
----------------------

Use separate resources for each environment.

Recommended separation:

* development API Gateway;
* staging API Gateway;
* production API Gateway;
* separate domains or subdomains;
* separate AWS credentials or roles;
* separate Django settings;
* separate databases.

Avoid pointing development API Gateway callbacks at production Django endpoints
or using production credentials in local development.

Rolling deployments
-------------------

During rolling deployments, existing WebSocket connections may remain open while
new code is deployed.

Design handlers to tolerate:

* clients connected with older JavaScript;
* messages from older pages;
* short periods where routes or handlers differ;
* clients reconnecting during deployment.

When making breaking changes to client message payloads, consider supporting
both old and new payloads temporarily.

Blue/green and multi-instance deployments
-----------------------------------------

Because AWS API Gateway owns the WebSocket connection and session state is stored
in the database, the Django application can run on multiple instances.

Make sure all instances share:

* the same database;
* compatible Django settings;
* access to the same AWS API Gateway configuration;
* the same session backend;
* the same secret key configuration, where required by Django sessions.

Sending messages from any instance should work as long as AWS credentials and
the database state are available.

Deployment smoke test
---------------------

After deploying, test the following:

#. open a browser page that uses WebSockets;
#. request a WebSocket token if enabled;
#. connect to the WebSocket endpoint;
#. confirm a ``WebSocketSession`` record is created;
#. send a message from the browser;
#. confirm Django handles the message;
#. send a message from Django to the browser;
#. broadcast to a channel;
#. disconnect the browser;
#. confirm the session is marked disconnected;
#. run cleanup commands;
#. review Django and API Gateway logs.

Troubleshooting
---------------

If deployment does not work, check:

* API Gateway target base endpoint;
* stage deployment status;
* custom domain mapping;
* DNS records;
* AWS region;
* IAM permissions;
* Django ``ALLOWED_HOSTS``;
* CSRF and session cookie settings;
* WebSocket token flow;
* browser console errors;
* API Gateway logs;
* Django logs.

See :doc:`troubleshooting`.

Related pages
-------------

See also:

* :doc:`quickstart`;
* :doc:`configuration`;
* :doc:`aws_iam_setup`;
* :doc:`api_gateway_setup`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`permissions`;
* :doc:`reconnecting_websocket`;
* :doc:`cleanup`;
* :doc:`troubleshooting`.
```