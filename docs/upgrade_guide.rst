Upgrade guide
=============

This guide explains how to upgrade Django-AWS-API-Gateway-WebSockets between
versions and highlights the areas most likely to need application changes.

Before upgrading
----------------

Before upgrading, review:

* :doc:`changelog`;
* :doc:`security`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`permissions`;
* :doc:`deployment`.

For production systems, test the upgrade in a staging environment before
deploying to production.

Recommended upgrade process
---------------------------

#. Read the changelog for all versions between your current version and the
   target version.
#. Check supported Python and Django versions.
#. Upgrade the package in a local or staging environment.
#. Apply database migrations.
#. Review WebSocket token behaviour.
#. Review rate limiting behaviour.
#. Review permission and handler restrictions.
#. Update frontend WebSocket connection code if required.
#. Run the test suite.
#. Test a full WebSocket connection through API Gateway.
#. Deploy to production.
#. Monitor connection, token, and rate limit errors after deployment.

Upgrade checklist
-----------------

Use this checklist for each upgrade.

Python and Django
~~~~~~~~~~~~~~~~~

* Your Python version is supported.
* Your Django version is supported.
* CI runs against the target Python and Django combination.
* Dependency constraints are updated if required.

Database
~~~~~~~~

* Migrations have been applied.
* New tables are present.
* Existing data has been reviewed.
* Cleanup commands are scheduled.

WebSocket connection flow
~~~~~~~~~~~~~~~~~~~~~~~~~

* The browser can request a WebSocket token if tokens are enabled.
* The browser includes ``ws_token`` in the connection URL.
* The browser requests a fresh token for reconnects.
* The connection creates a ``WebSocketSession`` record.
* Disconnection marks the session disconnected.

Security
~~~~~~~~

* WebSocket token protection is enabled where appropriate.
* Rate limiting is configured.
* Handler whitelisting is configured where appropriate.
* Django permissions are configured where appropriate.
* Channel access is validated server-side.
* IAM permissions are still appropriate.

Operations
~~~~~~~~~~

* Cleanup commands are scheduled.
* Logs are monitored after deployment.
* API Gateway routes are deployed.
* Custom domains and DNS still resolve correctly.
* Stale sessions are handled.

Upgrading from pre-token versions
---------------------------------

Recent versions of the package support WebSocket token protection.

If you are upgrading from a version where clients connected directly without
tokens, you may need to update your frontend.

Old connection pattern
~~~~~~~~~~~~~~~~~~~~~~

Older clients may connect directly:

.. code-block:: javascript

   const socket = new WebSocket("wss://ws.example.com?channel=notifications");

Token-protected connection pattern
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With WebSocket token protection enabled, the client should:

#. request a token from Django;
#. connect with the token;
#. request a fresh token for every reconnect.

Example connection URL:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Add the token endpoint
~~~~~~~~~~~~~~~~~~~~~~

Add the token view to your URL configuration.

.. code-block:: python

   from django.urls import path

   from django_aws_api_gateway_websockets.views import WebSocketTokenView

   urlpatterns = [
       path(
           "api/ws-token/",
           WebSocketTokenView.as_view(),
           name="websocket_token",
       ),
   ]

Update the browser client
~~~~~~~~~~~~~~~~~~~~~~~~~

Example token request:

.. code-block:: javascript

   function getCookie(name) {
       let cookieValue = null;

       if (document.cookie && document.cookie !== "") {
           const cookies = document.cookie.split(";");

           for (let i = 0; i < cookies.length; i++) {
               const cookie = cookies[i].trim();

               if (cookie.substring(0, name.length + 1) === `${name}=`) {
                   cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                   break;
               }
           }
       }

       return cookieValue;
   }

   async function getWebSocketToken() {
       const csrfToken = getCookie("csrftoken");

       const response = await fetch("/api/ws-token/", {
           method: "POST",
           headers: {
               "X-CSRFToken": csrfToken,
               "Content-Type": "application/json"
           },
           credentials: "same-origin"
       });

       if (!response.ok) {
           throw new Error(`Token request failed: ${response.status}`);
       }

       const data = await response.json();
       return data.token;
   }

Example token-protected connection:

.. code-block:: javascript

   async function connectWebSocket() {
       const token = await getWebSocketToken();
       const channel = "notifications";

       const websocketUrl = (
           `wss://ws.example.com?ws_token=${encodeURIComponent(token)}` +
           `&channel=${encodeURIComponent(channel)}`
       );

       return new WebSocket(websocketUrl);
   }

Temporary compatibility option
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you need time to update clients, you can temporarily disable WebSocket token
validation on a specific view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class LegacyWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           return None

This is not recommended for authenticated production WebSocket endpoints.

Prefer updating clients to use WebSocket tokens.

See :doc:`websocket_tokens`.

Upgrading reconnecting clients
------------------------------

If your frontend uses a reconnecting WebSocket library, make sure reconnects do
not reuse an old token.

Tokens are single-use.

Bad reconnect behaviour
~~~~~~~~~~~~~~~~~~~~~~~

This pattern is not safe with token protection:

.. code-block:: javascript

   const socket = new ReconnectingWebSocket(
       "wss://ws.example.com?ws_token=already-used-token&channel=general"
   );

If the connection drops, the reconnecting client may try to reuse the same token.

Recommended reconnect behaviour
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use a reconnect flow that requests a fresh token before opening a new
connection.

.. code-block:: javascript

   async function connectWebSocket() {
       const token = await getWebSocketToken();

       const websocketUrl = (
           `wss://ws.example.com?ws_token=${encodeURIComponent(token)}` +
           "&channel=general"
       );

       const socket = new ReconnectingWebSocket(websocketUrl, null, {
           debug: false,
           reconnectInterval: 3000,
           maxReconnectInterval: 10000,
           reconnectDecay: 1.5,
           timeoutInterval: 5000,
           maxReconnectAttempts: null
       });

       return socket;
   }

See :doc:`reconnecting_websocket`.

Upgrading for rate limiting
---------------------------

Recent versions include connection rate limiting.

By default, connection attempts are limited by IP address and by authenticated
user where available.

The default connection limit is:

.. code-block:: text

   20 connection attempts per minute

If your frontend reconnects aggressively, users may hit the rate limit after an
upgrade.

Customise limits
~~~~~~~~~~~~~~~~

You can customise limits on your WebSocket view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 40
       RATE_LIMIT_WINDOW_MINUTES = 5

       def default(self, request, *args, **kwargs):
           return None

Temporarily disable rate limiting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For controlled internal endpoints, you can disable connection rate limiting.

.. code-block:: python

   class InternalWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = False

       def default(self, request, *args, **kwargs):
           return None

Disabling rate limiting is not recommended for public endpoints.

See :doc:`rate_limiting`.

Upgrading for permission checks
-------------------------------

The package supports Django permission checks on WebSocket views.

If you add permissions during an upgrade, test:

* users without permissions;
* users with one required permission;
* users with all required permissions;
* anonymous users;
* object-level access rules.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
       ]

       def default(self, request, *args, **kwargs):
           return None

For object-level rules, check permissions inside the handler.

See :doc:`permissions`.

Upgrading handler selection
---------------------------

Older examples may use ``action`` for both API Gateway route selection and
Django handler selection.

Newer code may use a separate ``handler`` field for Django-side handler
selection.

Both approaches can work, but your client payloads, API Gateway route selection
expression, and Django view configuration must agree.

Action-based payload
~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "action": "chat_message",
     "message": "Hello"
   }

Handler-based payload
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "handler": "chat_message",
     "message": "Hello"
   }

Recommended approach
~~~~~~~~~~~~~~~~~~~~

For simple projects, using ``action`` everywhere may be easiest.

For larger projects, consider using:

* ``action`` for API Gateway route selection;
* ``handler`` for Django-side handler selection.

If you change the payload shape, update the frontend and tests at the same time.

See :doc:`concepts` and :doc:`client_integration`.

Upgrading custom routes
-----------------------

If your project uses additional API Gateway routes, check that:

* custom route records still exist;
* integration URLs are correct;
* the API Gateway stage has been redeployed;
* route keys match client payloads;
* Django views still contain matching handlers;
* handler whitelists include the expected handlers.

After changing routes, test the route through API Gateway rather than only
through Django's test client.

See :doc:`adding_new_routes`.

Upgrading cleanup tasks
-----------------------

Recent versions store operational records for tokens and rate limiting.

Schedule cleanup for:

* disconnected WebSocket sessions;
* expired or used WebSocket tokens;
* old rate limit records.

Commands:

.. code-block:: console

   python manage.py clearWebSocketSessions
   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

If you previously scheduled an older or differently named cleanup command, update
your scheduler.

Common places to check:

* cron;
* systemd timers;
* Celery Beat;
* Kubernetes CronJobs;
* ECS scheduled tasks;
* Heroku Scheduler;
* platform scheduled jobs.

See :doc:`cleanup`.

Upgrading AWS configuration
---------------------------

After upgrading, review AWS-related configuration:

* API Gateway records;
* custom domain mappings;
* route selection expression;
* stage name;
* AWS region;
* IAM permissions;
* certificate ARN;
* hosted zone ID.

If the upgrade adds features that create or update AWS resources, the deployment
identity may need additional permissions.

Avoid using broad administrator permissions permanently. Restrict permissions
after setup where possible.

See :doc:`aws_iam_setup`.

Upgrading Django settings
-------------------------

Review settings that affect WebSockets, sessions, and CSRF.

Important settings include:

* ``ALLOWED_HOSTS``;
* ``CSRF_TRUSTED_ORIGINS``;
* ``CSRF_COOKIE_DOMAIN``;
* ``SESSION_COOKIE_DOMAIN``;
* ``CSRF_COOKIE_SAMESITE``;
* ``SESSION_COOKIE_SAMESITE``;
* ``CSRF_COOKIE_SECURE``;
* ``SESSION_COOKIE_SECURE``;
* ``AWS_GATEWAY_REGION_NAME``;
* ``AWS_IAM_PROFILE``.

If your WebSocket endpoint uses a different subdomain from your main site, test
the full authenticated token flow after changing settings.

See :doc:`settings` and :doc:`configuration`.

Upgrading tests
---------------

After upgrading, add or update tests for:

* token generation;
* token reuse rejection;
* token-protected connection;
* connection rate limiting;
* handler selection;
* permission checks;
* channel access;
* message sending;
* stale session cleanup;
* management commands.

Run the project tests:

.. code-block:: console

   coverage erase
   python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings
   coverage combine
   coverage report

See :doc:`testing`.

Staging validation
------------------

Before deploying to production, validate the upgrade in staging.

Recommended checks:

#. open a page that uses WebSockets;
#. request a WebSocket token;
#. connect to API Gateway with the token;
#. confirm a ``WebSocketSession`` is created;
#. send a message from the browser;
#. confirm the correct handler is called;
#. send a message from Django to the browser;
#. reconnect and confirm a fresh token is used;
#. change channel if your application supports it;
#. trigger a permission failure and confirm it is denied;
#. trigger cleanup commands;
#. review Django and API Gateway logs.

Production rollout
------------------

For production rollout:

* deploy during a low-traffic window if possible;
* ensure migrations run before new code depends on new tables;
* deploy frontend and backend changes together if payloads changed;
* monitor token failures and rate limit failures;
* monitor WebSocket connection errors;
* monitor API Gateway integration errors;
* keep rollback instructions available.

Rollback considerations
-----------------------

Rolling back may be complicated if:

* database migrations added required tables or fields;
* frontend code now expects token-protected connections;
* API Gateway routes were changed;
* handler names or payload shapes changed.

Before upgrading, decide how you would roll back:

* package version;
* Django code;
* frontend JavaScript;
* API Gateway configuration;
* scheduled cleanup tasks.

Common upgrade problems
-----------------------

Connections fail after upgrade
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* WebSocket token requirement;
* token endpoint URL;
* CSRF configuration;
* session cookie configuration;
* API Gateway target endpoint;
* API Gateway stage deployment;
* ``ALLOWED_HOSTS``;
* custom domain DNS.

Tokens work once, then fail
~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is expected if the same token is reused.

Tokens are single-use. Request a fresh token for reconnects.

Users hit rate limits
~~~~~~~~~~~~~~~~~~~~~

Check frontend reconnect behaviour.

A reconnect loop can quickly exceed connection limits or token generation
limits.

Adjust reconnect backoff and, if needed, server-side limits.

Handlers stop being called
~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* payload field names;
* ``action`` vs ``handler``;
* API Gateway route selection expression;
* allowed handlers;
* method names on the view.

Messages are not delivered
~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* sessions are connected;
* target channel is correct;
* AWS credentials are valid;
* API Gateway stage name is correct;
* stale sessions are cleaned up;
* message size is within AWS limits.

Recommended upgrade path
------------------------

For most projects, the safest path is:

#. upgrade the package in development;
#. run migrations;
#. update frontend to support WebSocket tokens;
#. add or update tests;
#. validate locally or through a development API Gateway;
#. deploy to staging;
#. validate full connection and messaging flow;
#. deploy to production;
#. monitor logs and metrics.

Related pages
-------------

See also:

* :doc:`changelog`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`permissions`;
* :doc:`client_integration`;
* :doc:`reconnecting_websocket`;
* :doc:`settings`;
* :doc:`deployment`;
* :doc:`testing`;
* :doc:`troubleshooting`;
* :doc:`cleanup`.
