Rate limiting
=============

Django-AWS-API-Gateway-WebSockets includes rate limiting to help protect your
WebSocket endpoints from excessive connection attempts and excessive WebSocket
token generation.

Rate limiting is part of the project's defence-in-depth approach. It is intended
to reduce abuse, accidental reconnect storms, and unnecessary load on your
Django application and AWS API Gateway integration.

What is rate limited?
---------------------

The project currently applies rate limiting in two places:

* WebSocket connection attempts;
* WebSocket token generation.

Connection attempt rate limiting protects the ``$connect`` flow.

Token generation rate limiting protects the HTTP endpoint that issues short
lived, single-use WebSocket tokens.

Connection attempt rate limiting
--------------------------------

Connection attempt rate limiting is handled when a client attempts to open a new
WebSocket connection.

By default, the base WebSocket view allows:

.. code-block:: text

   20 connection attempts per minute

The rate limit is checked using:

* the client IP address;
* the authenticated Django user, if available.

If either the IP address or authenticated user exceeds the configured limit, the
connection is rejected.

Default connection limit settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The default values are defined on the base WebSocket view:

.. code-block:: python

   RATE_LIMIT_ENABLED = True
   RATE_LIMIT_MAX_ATTEMPTS = 20
   RATE_LIMIT_WINDOW_MINUTES = 5

This means that a client can make up to 20 connection attempts within a
5-minute window.

How connection attempts are tracked
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each connection attempt is recorded in the database.

The stored information includes:

* the client IP address;
* the authenticated user, if available;
* the attempt time;
* whether the attempt was successful.

This allows the project to check recent connection attempts for the same IP
address or user before accepting a new connection.

Customising connection limits
-----------------------------

You can customise the connection rate limit by overriding class attributes on
your WebSocket view.

Example: stricter limit
~~~~~~~~~~~~~~~~~~~~~~~

This example allows only 5 connection attempts every 10 minutes.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 5
       RATE_LIMIT_WINDOW_MINUTES = 10

       def default(self, request, *args, **kwargs):
           # Handle messages here.
           return None

Example: more permissive limit
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This example allows 60 connection attempts every 5 minutes.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class DashboardWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 60
       RATE_LIMIT_WINDOW_MINUTES = 5

       def default(self, request, *args, **kwargs):
           # Handle messages here.
           return None

Example: disable connection rate limiting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can disable connection rate limiting on a specific view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class InternalWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = False

       def default(self, request, *args, **kwargs):
           # Handle messages here.
           return None

Disabling rate limiting is not recommended for public WebSocket endpoints.

Token generation rate limiting
------------------------------

When WebSocket token protection is enabled, clients must request a short-lived
token before opening a WebSocket connection.

The token generation endpoint is also rate limited.

By default, the token endpoint allows:

.. code-block:: text

   10 tokens per user per minute

This helps prevent a client from repeatedly generating tokens and creating
unnecessary database records.

How token generation limiting works
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When an authenticated user requests a WebSocket token, the project counts how
many tokens that user has generated during the previous minute.

If the user has reached the limit, the token request is rejected.

The default token generation limit is applied by the token view.

Customising token generation limits
-----------------------------------

The built-in token view uses a default limit of 10 tokens per minute.

If you need a different limit, create a custom token view and call the token
model methods directly.

Example: custom token view
~~~~~~~~~~~~~~~~~~~~~~~~~~

This example allows 30 tokens per user per minute.

.. code-block:: python

   from django.http import HttpResponseForbidden
   from django.http import JsonResponse
   from django.views import View

   from django_aws_api_gateway_websockets.models import WebSocketToken


   class CustomWebSocketTokenView(View):
       MAX_TOKENS_PER_MINUTE = 30

       def post(self, request, *args, **kwargs):
           if not request.user.is_authenticated:
               return HttpResponseForbidden("Authentication required")

           if not request.session.session_key:
               request.session.create()

           allowed = WebSocketToken.check_rate_limit(
               request.user,
               max_tokens_per_minute=self.MAX_TOKENS_PER_MINUTE,
           )

           if not allowed:
               return HttpResponseForbidden("Rate limit exceeded")

           token = WebSocketToken.generate_token(
               user=request.user,
               session_key=request.session.session_key,
           )

           return JsonResponse(
               {
                   "token": token.token,
                   "expires_in": 60,
               }
           )

Then use your custom token view in your URL configuration.

.. code-block:: python

   from django.urls import path

   from .views import CustomWebSocketTokenView

   urlpatterns = [
       path(
           "api/ws-token/",
           CustomWebSocketTokenView.as_view(),
           name="websocket_token",
       ),
   ]

Choosing suitable limits
------------------------

The right limits depend on your application.

For a typical public application, the defaults are a reasonable starting point:

.. code-block:: text

   20 connection attempts per minute
   20 token requests per minute

You may want stricter limits for:

* unauthenticated or public pages;
* expensive connection setup logic;
* high-risk endpoints;
* applications where users should rarely reconnect.

You may want more permissive limits for:

* dashboards with frequent network changes;
* mobile clients;
* internal systems;
* applications using aggressive reconnect behaviour;
* development or staging environments.

Reconnect behaviour
-------------------

If you use a reconnecting WebSocket client, make sure the reconnect settings do
not conflict with your rate limits.

For example, a reconnect interval of 3 seconds can produce many connection
attempts in a short period if a client cannot connect successfully.

A safer reconnect strategy usually includes:

* a short initial reconnect delay;
* a maximum reconnect delay;
* exponential backoff;
* a limit on very rapid retries;
* fetching a fresh WebSocket token for each new connection when token protection
  is enabled.

Example client-side reconnect settings:

.. code-block:: javascript

   const socket = new ReconnectingWebSocket(websocketUrl, null, {
       debug: false,
       reconnectInterval: 3000,
       maxReconnectInterval: 10000,
       reconnectDecay: 1.5,
       timeoutInterval: 5000,
       maxReconnectAttempts: null
   });

If your users are hitting rate limits during normal use, review both the server
limits and the client reconnect strategy.

Cleaning up rate limit records
------------------------------

Rate limit checks use database records. Old records should be cleaned up
regularly to avoid unnecessary database growth.

The project includes a cleanup command for old WebSocket token and rate limit
records.

Run it manually with:

.. code-block:: console

   python manage.py cleanupWebSocketTokens

You can also pass cleanup options if supported by your installed version.

For example:

.. code-block:: console

   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

A common production approach is to run this command every few minutes using
cron, Celery Beat, a container scheduler, or your platform's scheduled task
system.

Example cron entry:

.. code-block:: text

   */5 * * * * cd /path/to/project && /path/to/venv/bin/python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

Operational guidance
--------------------

Monitor rate limiting in production so you can distinguish between normal client
behaviour and suspicious activity.

Useful things to monitor include:

* rejected WebSocket connections;
* rejected token requests;
* connection attempts by IP address;
* connection attempts by user;
* reconnect frequency;
* database growth in rate limit tables;
* frontend error logs.

If legitimate users are regularly rate limited, consider:

* increasing ``RATE_LIMIT_MAX_ATTEMPTS``;
* increasing or decreasing ``RATE_LIMIT_WINDOW_MINUTES`` depending on the
  desired behaviour;
* adjusting reconnect settings in the frontend;
* checking whether clients are reconnecting unnecessarily;
* checking whether WebSocket tokens are being requested repeatedly.

Security notes
--------------

Rate limiting should not be your only protection.

For production systems, also consider:

* requiring authentication where appropriate;
* using WebSocket token protection;
* validating channel names;
* validating message size and structure;
* using Django permissions for restricted handlers;
* logging suspicious behaviour;
* cleaning up stale sessions and old rate limit records.

Related pages
-------------

See also:

* :doc:`reconnecting_websocket`;
* :doc:`cleanup`;
* :doc:`configuration`;
* :doc:`api_gateway_setup`.
