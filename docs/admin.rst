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
* provisioning status;
* whether the API has been created;
* the deployment ID;
* whether the custom domain has been created;
* created and updated timestamps.

.. versionchanged:: 4.1
   The list page and the change page show ``deployment_id``, and the change page
   shows ``api_created``. Both are read-only: AWS sets them.

Filters
~~~~~~~

The admin includes filters for:

* provisioning status;
* API created;
* custom domain created.

Provisioning status
~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.1

Creating the API in AWS takes several calls. The ``Provisioning status`` field
records how far they got, and each step is saved as soon as it succeeds:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Status
     - Meaning
   * - Pending
     - Nothing has been created in AWS.
   * - Creating
     - A run has started and is creating the API. A second run is refused while this shows, so two requests cannot create two APIs.
   * - API created
     - The API exists in AWS and its ID is saved. The routes are not finished.
   * - Routes created
     - The routes exist. The stage and deployment are not finished.
   * - Deployed
     - The API is complete.
   * - Custom domain created
     - The custom domain exists. Its mapping to the API is not finished.
   * - Custom domain mapped
     - The custom domain is complete.

If a step fails, the status stays at the last step that worked, and the
**Last error** field shows what stopped it: the kind of error, and for an AWS
error its code. Fix the cause, then run the same action again. It continues from
the recorded status and does not create the API a second time.

If a run fails before AWS creates the API, the status returns to Pending. If the
process stops after AWS creates the API but before the ID is saved, for example
because the database goes down, the status stays at Creating and the next run
is refused with a message. Check AWS. If the API is not there, set the status to
Pending. If it is, delete it or record its ID, and set the status to match.

The ``Create API Gateway`` and ``Create Custom Domain`` actions resume in this
way. So do the ``createApiGateway`` and ``createCustomDomain`` management
commands. See :doc:`troubleshooting`.

The ``API created`` and ``Custom domain created`` fields keep their earlier
meaning: they become true as soon as the API or the custom domain exists in AWS,
even if later steps have not finished. Use the status to see whether a gateway is
complete.

.. note::

   A record created before this version, or one you registered by hand for an API
   that already exists, shows ``Pending`` with ``API created`` set. It is treated
   as complete and is never provisioned again, because nothing shows how far an
   older run got.

   If one of these is in fact half built, set ``Provisioning status`` to match
   what exists in AWS. For an API with no routes, choose *API created*. For one
   with routes but no stage, choose *Routes created*. Then run the action again.

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

Sync to AWS and Sync from AWS actions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.1

Two actions compare the local record with the deployed API in AWS. Both work only
on a deployed API Gateway, and report an error for any other record.

Both work whatever ``WEBSOCKETS["push_changes_to_aws"]`` is set to. With that
setting off, saving a record changes only the local record, and these actions are
how you change AWS. See :ref:`api-gateway-auto-sync`.

``Sync to AWS``
   Writes the local values to AWS: the API name, description and selection
   expressions, the URL of each default route, and the URL and key of each
   additional route. It creates a local additional route that is missing in AWS,
   and deploys the stage if anything changed. It changes only what differs, so
   running it on a record that already matches changes nothing. It never deletes
   a route that exists only in AWS.

``Sync from AWS``
   Reads the deployed API in AWS into the local records: the same values, the
   base URL taken from the ``$default`` route, the stage description and the
   deployment ID. It adds a local additional route for each route that exists
   only in AWS. It deletes nothing: a local route that is missing in AWS is kept
   and marked as not deployed, so ``Sync to AWS`` creates it again.

Each action reports what it changed for each selected record. Both are logged
server-side and need the change permission, in the same way as the other actions.

Changes made on this page are also sent to AWS when you save. See
:ref:`api-gateway-auto-sync`.

Required permissions
~~~~~~~~~~~~~~~~~~~~

The Django admin user needs the appropriate Django admin permissions.

.. versionchanged:: 4.1
   The ``Create API Gateway``, ``Create Custom Domain``, ``Sync to AWS`` and
   ``Sync from AWS`` actions are available
   only to users who have the ``Can change api gateway`` permission, and to
   superusers. A user who can only view the page no longer sees them. Django
   enforces this when the action is submitted, not only in the dropdown.

These actions create resources in AWS with the credentials of the Django
application, so give the change permission only to people you trust to do that.

The AWS credentials available to Django also need permissions to create or update
API Gateway resources.

.. note::

   Saving an additional route deploys it to API Gateway immediately, and its
   integration URL can be any URL. Give the ``Can add api gateway additional
   route`` and ``Can change api gateway additional route`` permissions with the
   same care.

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

.. versionchanged:: 4.1
   The page is read-only. Sessions are created by the connect route, and editing the ``user`` of a session would
   attach a live connection to any account. You can still view and delete sessions with the matching permissions.

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

ChannelPermission admin
-----------------------

The ``ChannelPermission`` admin page controls who may join each WebSocket
channel. See :doc:`channel_permissions` for what the access levels and rules mean.

.. versionadded:: 4.1

The list page shows the channel name, the access level, a summary of the rules
and the last update. You can filter by access level and search by channel name
or description.

Each channel has a **Channel permission rules** section. Each rule holds one or
more Django permissions, and the user needs all the permissions in a rule. The
user needs to satisfy any one rule. The rules are used only when the access
level is *Requires Django permissions*.

.. warning::

   Anyone who can add or change channel permissions controls who can join
   channels. Give that permission only to people you trust with that decision.

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
* email.

Read-only behaviour
~~~~~~~~~~~~~~~~~~~

Token records are read-only in the admin.

The token value is intentionally shown only as a preview in list views to reduce
the risk of exposing full token values.

.. versionchanged:: 4.1
   The session key is neither shown nor searchable. A Django session key works as a login credential until its session
   expires, so ``WebSocketToken.session_key`` now stores a keyed SHA-256 hash of it (see
   :func:`django_aws_api_gateway_websockets.models.hash_session_key`) instead of the key itself.

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

   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

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

   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

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

.. _admin-integration-permissions:

Who may change where traffic goes
---------------------------------

.. warning::

   The change permission on **API gateways** and **additional routes** is as
   powerful as a superuser's for your WebSocket traffic. The ``target_base_endpoint``
   of a gateway and the ``integration_url`` of a route decide where API Gateway
   sends every connect, disconnect and message event. Each request carries the
   connection ID and, if you set one, the :doc:`gateway secret <gateway_secret>`.
   Someone who can change these fields can send those requests to a server they
   control, and answer them.

Give the change permission only to people who may redirect your traffic, and put
them in a group of their own. To limit the damage, set
``WEBSOCKETS["allowed_integration_hosts"]`` to your own hosts. A save that points
an integration anywhere else is then refused. See :doc:`settings`.

Saving an additional route validates it, as saving an API gateway does. Before
version 4.1, ``ApiGatewayAdditionalRoute.save()`` did not call ``full_clean()``.
A save with ``update_fields`` still skips validation.

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
