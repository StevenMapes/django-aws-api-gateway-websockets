Django Admin
============

Django-AWS-API-Gateway-WebSockets includes Django Admin integration for managing
API Gateway configuration, additional routes, WebSocket sessions, WebSocket
tokens, and rate limit records.

The admin is useful for:

* creating API Gateway records;
* creating AWS API Gateway resources;
* creating custom domain mappings;
* managing additional routes;
* inspecting active and historical WebSocket sessions;
* reviewing WebSocket token records;
* reviewing rate limit records;
* debugging setup and deployment issues.

Enable the admin
----------------

To use the admin integration, make sure the package is installed and added to
``INSTALLED_APPS``.

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "django_aws_api_gateway_websockets",
   ]

Then run migrations:

.. code-block:: console

   python manage.py migrate

The package's models will appear in Django Admin after the application is
installed.

Admin models
------------

The following models are registered with Django Admin:

* ``ApiGateway``;
* ``ApiGatewayAdditionalRoute``;
* ``WebSocketSession``;
* ``WebSocketToken``;
* ``ConnectionRateLimit``.

ApiGateway admin
----------------

The ``ApiGateway`` admin page is used to configure and deploy AWS API Gateway
WebSocket APIs.

List display
~~~~~~~~~~~~

The list page shows useful deployment information, including:

* API name;
* custom domain name;
* default channel name;
* AWS API ID;
* AWS API endpoint;
* API Gateway domain name;
* whether the API has been created;
* whether the custom domain has been created;
* created and updated timestamps.

Filters
~~~~~~~

The admin includes filters for:

* API created;
* custom domain created.

Search
~~~~~~

You can search by:

* API name;
* domain name.

Additional routes inline
~~~~~~~~~~~~~~~~~~~~~~~~

The ``ApiGateway`` admin includes inline forms for
``ApiGatewayAdditionalRoute`` records.

This lets you manage custom route mappings while editing the parent API Gateway
record.

Create API Gateway action
~~~~~~~~~~~~~~~~~~~~~~~~~

The ``Create API Gateway`` admin action creates the AWS API Gateway WebSocket API
for selected records.

To use it:

#. open the ``ApiGateway`` list page;
#. select the API Gateway record;
#. choose ``Create API Gateway`` from the actions dropdown;
#. click ``Go``.

The action creates the AWS API Gateway resources if they do not already exist.

After successful creation, the record is updated with AWS values such as the API
ID and API endpoint.

The action also logs administrative activity server-side.

Create custom domain action
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``Create Custom Domain`` admin action creates the custom domain mapping for
selected API Gateway records.

To use it:

#. make sure the API Gateway has already been created;
#. make sure the record has a domain name and certificate ARN;
#. open the ``ApiGateway`` list page;
#. select the API Gateway record;
#. choose ``Create Custom Domain`` from the actions dropdown;
#. click ``Go``.

After successful creation, the record is updated with the API Gateway domain
name and custom domain state.

If using external DNS, use the API Gateway domain name shown on the record when
creating your DNS entry.

Required permissions
~~~~~~~~~~~~~~~~~~~~

The Django admin user needs the appropriate Django admin permissions.

The AWS credentials available to Django also need permissions to create or update
API Gateway resources.

See :doc:`aws_iam_setup`.

ApiGatewayAdditionalRoute admin
-------------------------------

The ``ApiGatewayAdditionalRoute`` admin page manages custom WebSocket route
mappings.

Use additional routes when different API Gateway route keys should call
different Django endpoints.

List display
~~~~~~~~~~~~

The list page shows:

* name;
* parent API Gateway;
* route key;
* integration URL;
* deployed state.

Filters
~~~~~~~

You can filter by parent API Gateway.

Search
~~~~~~

You can search by route name and route key.

Common fields
~~~~~~~~~~~~~

``api_gateway``
   The parent API Gateway record.

``name``
   Human-friendly name for the route.

``route_key``
   The API Gateway route key.

``integration_url``
   The Django endpoint this route should call.

``deployed``
   Whether this route has been deployed to AWS.

Deployment behaviour
~~~~~~~~~~~~~~~~~~~~

If the parent API Gateway has already been deployed, saving an additional route
can deploy that route to AWS.

If the parent API Gateway has not been deployed yet, additional routes are
created during the main API Gateway deployment.

See :doc:`adding_new_routes`.

WebSocketSession admin
----------------------

The ``WebSocketSession`` admin page shows active and historical WebSocket
connection records.

This is useful for debugging connection issues and understanding which users are
connected to which channels.

List display
~~~~~~~~~~~~

The list page shows:

* connection ID;
* channel name;
* API Gateway;
* user;
* connected state;
* request count;
* created timestamp;
* updated timestamp.

Filters
~~~~~~~

You can filter by:

* connected state;
* channel name.

Search
~~~~~~

You can search by:

* connection ID;
* channel name.

Common uses
~~~~~~~~~~~

Use this page to answer questions such as:

* is a connection being created when the browser connects?
* which channel did the client join?
* which user is associated with the connection?
* is the connection still marked as connected?
* how many requests have been handled for the session?
* are stale sessions accumulating?

Cleaning sessions
~~~~~~~~~~~~~~~~~

Disconnected sessions can be removed with:

.. code-block:: console

   python manage.py clearWebSocketSessions

See :doc:`cleanup`.

WebSocketToken admin
--------------------

The ``WebSocketToken`` admin page shows token records used for WebSocket token
protection.

Tokens are created programmatically by the token endpoint. They should not be
created or edited manually in Django Admin.

List display
~~~~~~~~~~~~

The list page shows:

* a shortened token preview;
* user;
* session key;
* created timestamp;
* whether the token has been used.

Filters
~~~~~~~

You can filter by:

* used state;
* created timestamp.

Search
~~~~~~

You can search by:

* username;
* email;
* session key.

Read-only behaviour
~~~~~~~~~~~~~~~~~~~

Token records are read-only in the admin.

The token value is intentionally shown only as a preview in list views to reduce
the risk of exposing full token values.

Common uses
~~~~~~~~~~~

Use this page to debug questions such as:

* is the browser successfully requesting tokens?
* are tokens being created for the expected user?
* are tokens being marked as used?
* are old tokens accumulating?
* are users requesting tokens too frequently?

Cleaning tokens
~~~~~~~~~~~~~~~

Expired and used tokens should be cleaned up regularly.

.. code-block:: console

   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

See :doc:`websocket_tokens` and :doc:`cleanup`.

ConnectionRateLimit admin
-------------------------

The ``ConnectionRateLimit`` admin page shows connection attempt records used by
the rate limiting system.

Records are created programmatically when clients attempt to connect.

List display
~~~~~~~~~~~~

The list page shows:

* IP address;
* user, where available;
* attempt time;
* whether the attempt was successful.

Filters
~~~~~~~

You can filter by:

* successful state;
* attempt time.

Search
~~~~~~

You can search by:

* IP address;
* username;
* email address.

Read-only behaviour
~~~~~~~~~~~~~~~~~~~

Rate limit records are read-only in the admin.

They are created by the connection flow and should not be edited manually.

Common uses
~~~~~~~~~~~

Use this page to debug questions such as:

* is a client hitting the connection rate limit?
* are failed connection attempts coming from the same IP address?
* are reconnect loops creating many attempts?
* are anonymous or authenticated users being rate limited?
* are rate limit records accumulating?

Cleaning rate limit records
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Old rate limit records should be cleaned up regularly.

.. code-block:: console

   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

Despite the command name, this command also cleans old rate limit records.

See :doc:`rate_limiting` and :doc:`cleanup`.

Recommended admin workflow
--------------------------

For a new API Gateway setup, a typical admin workflow is:

#. create an ``ApiGateway`` record;
#. enter the target base endpoint;
#. configure the stage name;
#. configure the route selection expression;
#. add the custom domain and certificate ARN if required;
#. add additional routes if required;
#. save the record;
#. run the ``Create API Gateway`` admin action;
#. confirm the API ID and API endpoint were populated;
#. run the ``Create Custom Domain`` action if using a custom domain;
#. configure DNS;
#. connect from a browser;
#. inspect ``WebSocketSession`` records to confirm connections are recorded.

Admin security
--------------

The admin can create and update AWS resources, so access should be restricted.

Recommended controls:

* only trusted staff users should access these admin pages;
* use Django permissions and groups to limit access;
* use strong authentication for Django Admin;
* enable multi-factor authentication where possible;
* avoid exposing Django Admin publicly where possible;
* review server logs for admin actions;
* use least-privilege AWS credentials.

AWS credentials used by Django should be restricted to the actions required by
your deployment.

See :doc:`security` and :doc:`aws_iam_setup`.

Audit logging
-------------

Admin actions log important events server-side, such as:

* API Gateway creation attempts;
* successful API Gateway creation;
* custom domain creation attempts;
* successful custom domain creation;
* errors during AWS resource creation.

Make sure your Django logging configuration stores these logs somewhere useful
in production.

Troubleshooting with admin
--------------------------

No WebSocketSession appears after connecting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* API Gateway target base endpoint;
* Django URL route;
* ``<slug:route>`` parameter name;
* API Gateway stage deployment;
* WebSocket token validation;
* Django logs.

Session appears but user is missing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* whether WebSocket tokens are enabled;
* whether the token request was authenticated;
* whether cookies are available across subdomains;
* session cookie configuration.

Tokens are created but connections fail
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* the token is included in the WebSocket URL;
* the token is not expired;
* the token is not reused;
* the session cookie is consistent between token request and connection.

Many rate limit records are created
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* reconnect loop behaviour;
* browser console errors;
* frontend token request behaviour;
* connection rate limit settings;
* whether clients are repeatedly failing to connect.

API Gateway action fails
~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* AWS credentials;
* AWS region;
* IAM permissions;
* target base endpoint;
* certificate ARN;
* custom domain configuration;
* Django server logs.

Related pages
-------------

See also:

* :doc:`models`;
* :doc:`api_gateway_setup`;
* :doc:`adding_new_routes`;
* :doc:`aws_iam_setup`;
* :doc:`security`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`cleanup`;
* :doc:`troubleshooting`.
