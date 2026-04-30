WebSocket tokens
================

Django-AWS-API-Gateway-WebSockets includes optional WebSocket token protection
for authenticated WebSocket connections.

WebSocket tokens are short-lived, single-use tokens that are requested over a
normal CSRF-protected Django HTTP endpoint before the browser opens the
WebSocket connection.

They are designed to reduce the risk of cross-site request-forgery-style attacks
against authenticated WebSocket connections.

Why WebSocket tokens are needed
-------------------------------

WebSocket connections are opened by the browser using the WebSocket API rather
than by submitting a normal Django form.

The WebSocket connection request is handled by AWS API Gateway and then
forwarded to Django. Because of this, the WebSocket view cannot be protected in
exactly the same way as a normal Django POST view using Django's built-in CSRF
middleware.

To protect authenticated WebSocket connections, this package uses a separate
token flow:

#. the authenticated browser requests a WebSocket token from Django;
#. the token request is protected by normal Django CSRF checks;
#. Django creates a short-lived, single-use token;
#. the browser opens the WebSocket connection and includes the token;
#. the WebSocket view validates and consumes the token during ``$connect``.

This gives Django a way to confirm that the WebSocket connection was initiated
by a page that could make a valid CSRF-protected request.

Token properties
----------------

A WebSocket token is:

* generated for an authenticated user;
* bound to the current Django session key;
* valid for a short period;
* single-use;
* consumed during WebSocket connection;
* stored in the database so it can be validated and marked as used.

The default token lifetime is short. The client should connect as soon as the
token is received.

Default behaviour
-----------------

WebSocket token protection is enabled on the base WebSocket view by default.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       USE_WS_TOKEN = True

       def default(self, request, *args, **kwargs):
           return None

When ``USE_WS_TOKEN`` is enabled, the client must include a valid token in the
WebSocket connection URL.

Example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

If the token is missing, expired, already used, or does not match the current
session, the connection is rejected.

Token request endpoint
----------------------

The package provides a token view that can be added to your URL configuration.

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

The browser should make a ``POST`` request to this endpoint before opening the
WebSocket connection.

The token endpoint requires an authenticated user.

Example response:

.. code-block:: json

   {
     "token": "abc123...",
     "expires_in": 60
   }

Requesting a token from the browser
-----------------------------------

The token request should include the user's normal Django session cookie and a
valid CSRF token.

Example helper for reading a cookie:

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

Example function for requesting a WebSocket token:

.. code-block:: javascript

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

Opening the WebSocket connection
--------------------------------

After receiving the token, include it in the WebSocket URL using the
``ws_token`` query string parameter.

.. code-block:: javascript

   async function connectWebSocket() {
       const token = await getWebSocketToken();
       const channelName = "notifications";

       const websocketUrl = (
           `wss://ws.example.com?ws_token=${encodeURIComponent(token)}` +
           `&channel=${encodeURIComponent(channelName)}`
       );

       const socket = new WebSocket(websocketUrl);

       socket.onopen = function () {
           console.log("WebSocket connected");
       };

       socket.onmessage = function (event) {
           const message = JSON.parse(event.data);
           console.log("WebSocket message received:", message);
       };

       socket.onerror = function (event) {
           console.error("WebSocket error:", event);
       };

       socket.onclose = function (event) {
           console.log("WebSocket closed:", event.code, event.reason);
       };
   }

Using reconnecting clients
--------------------------

When using a reconnecting WebSocket client, do not reuse the same token.

Tokens are single-use. A reconnect should request a fresh token before opening a
new WebSocket connection.

A safe reconnection flow is:

#. connection closes;
#. browser requests a new token;
#. browser opens a new WebSocket connection with the new token;
#. token is consumed during ``$connect``.

Example using ``reconnecting-websocket``:

.. code-block:: javascript

   const websocketBaseUrl = "wss://ws.example.com";
   const tokenEndpoint = "/api/ws-token/";
   const channelName = "notifications";

   let socket = null;

   async function requestToken() {
       const csrfToken = getCookie("csrftoken");

       const response = await fetch(tokenEndpoint, {
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

   async function connectWebSocket() {
       let token;

       try {
           token = await requestToken();
       } catch (error) {
           console.error(error);
           setTimeout(connectWebSocket, 5000);
           return;
       }

       const websocketUrl = (
           `${websocketBaseUrl}?ws_token=${encodeURIComponent(token)}` +
           `&channel=${encodeURIComponent(channelName)}`
       );

       socket = new ReconnectingWebSocket(websocketUrl, null, {
           debug: false,
           reconnectInterval: 3000,
           maxReconnectInterval: 10000,
           reconnectDecay: 1.5,
           timeoutInterval: 5000,
           maxReconnectAttempts: null
       });

       socket.onopen = function () {
           console.log("WebSocket connected");
       };

       socket.onmessage = function (event) {
           const message = JSON.parse(event.data);
           console.log("Message received:", message);
       };

       socket.onclose = function () {
           setTimeout(function () {
               if (
                   socket.readyState === WebSocket.CLOSED ||
                   socket.readyState === WebSocket.CLOSING
               ) {
                   connectWebSocket();
               }
           }, 3000);
       };
   }

   connectWebSocket();

See :doc:`reconnecting_websocket` for a fuller reconnecting client example.

Token expiry
------------

Tokens are short-lived.

The token endpoint returns an ``expires_in`` value so the client knows how long
the token can be used for.

Example response:

.. code-block:: json

   {
     "token": "abc123...",
     "expires_in": 60
   }

The browser should open the WebSocket connection immediately after receiving the
token.

Do not request a token on page load and then wait for a long time before
connecting.

Single-use behaviour
--------------------

A token can only be used once.

When the WebSocket connection is established, the token is validated and marked
as used.

This means the following will fail:

* opening two WebSocket connections with the same token;
* reconnecting with an old token;
* reusing a token after the previous connection attempt;
* retrying after a failed connection without requesting a new token.

If the connection fails, request a new token before trying again.

Session binding
---------------

Tokens are bound to the Django session key that requested them.

The WebSocket connection must be opened by a client with the same session.

This helps prevent a token from being useful if copied into another browser,
session, or user context.

Authentication
--------------

The built-in token endpoint requires an authenticated Django user.

If the user is not authenticated, the token request is rejected.

For anonymous WebSocket use cases, you can either:

* disable WebSocket token validation for that specific view;
* implement your own token flow suitable for anonymous users;
* require authentication before allowing WebSocket access.

Disabling WebSocket tokens
--------------------------

You can disable WebSocket token validation on a specific view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class PublicWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           return None

Disabling token validation may be acceptable for public, anonymous, low-risk
WebSocket endpoints.

It is not recommended for authenticated WebSocket endpoints unless you have
another protection mechanism in place.

Custom token endpoints
----------------------

If the built-in token endpoint does not fit your application, you can create a
custom token view.

For example, you may want to:

* change token generation rate limits;
* add extra permission checks;
* restrict tokens to certain users;
* include additional response metadata;
* log token generation for audit purposes.

Example custom token view:

.. code-block:: python

   from django.http import HttpResponseForbidden
   from django.http import JsonResponse
   from django.views import View

   from django_aws_api_gateway_websockets.models import WebSocketToken


   class CustomWebSocketTokenView(View):
       def post(self, request, *args, **kwargs):
           if not request.user.is_authenticated:
               return HttpResponseForbidden("Authentication required")

           if not request.user.has_perm("chat.can_use_chat"):
               return HttpResponseForbidden("Permission denied")

           if not request.session.session_key:
               request.session.create()

           if not WebSocketToken.check_rate_limit(
               request.user,
               max_tokens_per_minute=10,
           ):
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

URL configuration:

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

Token generation rate limiting
------------------------------

Token generation is rate limited per user.

This helps protect the database from excessive token creation and helps reduce
abuse from clients that repeatedly request tokens.

If legitimate users hit the token limit, check whether the frontend is
requesting tokens too frequently.

Common causes include:

* requesting a token repeatedly before every message;
* reconnecting too aggressively;
* multiple browser tabs connecting at the same time;
* requesting a token long before opening the WebSocket;
* retry loops that do not use backoff.

Tokens should usually be requested only when opening a new WebSocket connection.

Cleaning up tokens
------------------

Expired and used tokens should be cleaned up regularly.

The project includes a management command for cleaning up token and rate limit
records.

Example:

.. code-block:: console

   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

A common production schedule is every five minutes.

Example cron entry:

.. code-block:: text

   */5 * * * * cd /path/to/project && /path/to/venv/bin/python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

See :doc:`cleanup`.

Troubleshooting
---------------

Connection rejected because token is missing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that the WebSocket URL includes the ``ws_token`` query string parameter.

Example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Connection rejected because token expired
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request the token immediately before opening the WebSocket connection.

Do not cache tokens for later use.

Connection rejected because token was already used
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request a new token for each new connection attempt.

This includes reconnects and room/channel changes.

Token request returns forbidden
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that:

* the user is authenticated;
* the browser is sending the Django session cookie;
* the request includes a valid CSRF token;
* the user has permission if using a custom token endpoint;
* token generation rate limiting has not been exceeded.

Reconnect loop causes token failures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Make sure your reconnect logic requests a fresh token before creating each new
WebSocket connection.

Also review reconnect backoff settings so the client does not request tokens too
quickly.

Production recommendations
--------------------------

For production applications:

* keep ``USE_WS_TOKEN`` enabled for authenticated WebSocket views;
* request tokens only immediately before opening a WebSocket connection;
* never reuse tokens;
* request a fresh token for reconnects;
* use reconnect backoff to avoid token request storms;
* keep token lifetimes short;
* clean up old tokens regularly;
* validate permissions before issuing tokens where appropriate;
* validate permissions again inside WebSocket handlers for object-level access.

Related pages
-------------

See also:

* :doc:`security`;
* :doc:`rate_limiting`;
* :doc:`reconnecting_websocket`;
* :doc:`client_integration`;
* :doc:`cleanup`;
* :doc:`permissions`;
* :doc:`troubleshooting`.
