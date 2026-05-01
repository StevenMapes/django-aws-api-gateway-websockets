Security
========

Django-AWS-API-Gateway-WebSockets includes several security features intended to
protect WebSocket connections handled through AWS API Gateway and Django.

This page explains the main security controls, how they work together, and what
you should consider when deploying the package in production.

Security model
--------------

This package uses AWS API Gateway as the WebSocket server and Django as the
application handler.

The browser or client connects to API Gateway. API Gateway then forwards
connection, disconnection, and message events to Django as HTTP requests.

Because Django receives HTTP requests from API Gateway, the package performs
several checks before trusting or processing those requests.

The security model includes:

* WebSocket token protection;
* connection rate limiting;
* token generation rate limiting;
* API Gateway validation;
* header validation;
* origin and host checks;
* connection ID validation;
* channel name validation;
* request body size limits;
* message size limits;
* handler whitelisting;
* Django permissions;
* stale session cleanup;
* generic error handling.

These controls are designed to work together as defence in depth.

WebSocket token protection
--------------------------

WebSocket token protection is designed to reduce the risk of cross-site
request-forgery-style attacks against authenticated WebSocket connections.

When enabled, the browser must first request a short-lived WebSocket token from
Django using a normal CSRF-protected HTTP request.

The client then includes that token when opening the WebSocket connection.

Example WebSocket URL:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

The token is:

* linked to the authenticated Django user;
* linked to the Django session key;
* short-lived;
* single-use;
* consumed when the connection is established.

This means a token should not be reused for reconnects. If the client needs to
reconnect, it should request a fresh token before opening a new WebSocket
connection.

See :doc:`websocket_tokens`.

CSRF considerations
-------------------

The WebSocket view itself needs to receive HTTP requests from AWS API Gateway.
These requests are not normal browser form submissions and do not include a
standard Django CSRF token in the way Django's CSRF middleware expects.

For that reason, the WebSocket endpoint is exempted from Django's standard CSRF
view protection.

This does not mean WebSocket connections should be left unprotected.

For authenticated WebSocket usage, use the package's WebSocket token mechanism.
The token is requested through a CSRF-protected HTTP endpoint before the
WebSocket connection is opened.

In production, the recommended approach is:

#. user loads a normal authenticated Django page;
#. page requests a WebSocket token using CSRF protection;
#. Django returns a short-lived single-use token;
#. browser opens the WebSocket connection with the token;
#. Django validates and consumes the token during the connection event.

Rate limiting
-------------

The package includes rate limiting for connection attempts.

By default, the base WebSocket view allows:

.. code-block:: text

   20 connection attempts per 5 minutes

The rate limit is checked using:

* the client IP address;
* the authenticated user, where available.

If the limit is exceeded, the connection is rejected.

You can customise the limits on your WebSocket view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 10
       RATE_LIMIT_WINDOW_MINUTES = 5

       def default(self, request, *args, **kwargs):
           return None

Token generation is also rate limited. By default, users are limited to a small
number of token requests per minute.

See :doc:`rate_limiting`.

API Gateway validation
----------------------

Incoming requests should come from API Gateway, not directly from arbitrary
clients.

The package validates the API Gateway source using the API Gateway records stored
in the database.

A view can also be restricted to a specific API Gateway ID.

This helps prevent requests from unknown API Gateway endpoints or direct HTTP
clients from being accepted as valid WebSocket events.

For production systems:

* only create API Gateway records for trusted gateways;
* avoid sharing development gateway configuration with production;
* use separate API Gateway records for separate environments;
* remove old or unused API Gateway records.

Header validation
-----------------

The package checks for expected headers that are normally sent by API Gateway.

These checks help confirm that the request has the expected API Gateway shape
before it is processed.

If you deploy behind additional proxies, CDNs, tunnels, or load balancers, make
sure the required headers are preserved.

For local development, tunnelling services can sometimes remove or alter
headers. If this happens, use debug logging and review your view configuration.

Origin and host checks
----------------------

During connection, the package checks host and origin information.

This helps ensure that the connection request is consistent with the Django host
configuration and the origin that initiated the connection.

For production deployments, configure Django settings carefully:

* ``ALLOWED_HOSTS`` should include the correct application hosts;
* ``CSRF_TRUSTED_ORIGINS`` should include the required HTTPS origins;
* cookie domains should be configured correctly if using subdomains;
* session and CSRF cookies should be scoped intentionally.

If your main site and WebSocket endpoint use different subdomains, review
:doc:`api_gateway_setup` and :doc:`configuration`.

Connection ID validation
------------------------

API Gateway provides a connection ID for each WebSocket connection.

The package validates the connection ID format before using it.

This reduces the risk of malformed values being stored or used by the
application.

Channel name validation
-----------------------

Channels are used to group WebSocket sessions.

For example, you might use channels for:

* chat rooms;
* dashboards;
* user notifications;
* tenant-specific updates;
* document collaboration;
* background task progress.

The package validates channel names to keep them within an expected length and
character set.

When designing channel names, avoid including sensitive information unless it is
strictly required. Prefer opaque identifiers or safe slugs over raw user input.

For example, prefer:

.. code-block:: text

   room_123
   tenant_456
   notifications_user_789

over values containing emails, names, or sensitive business data.

Request body validation
-----------------------

Incoming request bodies are parsed as JSON.

The package limits the maximum request body size to reduce the risk of oversized
payloads.

For production applications, your handler methods should still validate the
message content they expect.

For example, validate:

* required fields;
* field types;
* maximum string lengths;
* allowed actions;
* permission to access the requested resource;
* whether the current user can send to the requested channel.

Do not trust client-provided data simply because it arrived through API Gateway.

Message size validation
-----------------------

AWS API Gateway WebSocket messages have size limits.

The package validates outgoing message size before sending messages back to
clients.

If your application sends larger payloads, consider sending a smaller message
over WebSocket and letting the client fetch the full resource over HTTPS.

For example:

.. code-block:: json

   {
     "type": "resource_updated",
     "resource_id": 123,
     "fetch_url": "/api/resources/123/"
   }

Handler whitelisting
--------------------

WebSocket messages can request a handler by name.

To avoid arbitrary method invocation, the package checks that requested handlers
are explicitly allowed.

Handler names starting with private method prefixes should not be callable from
client messages.

When building views:

* expose only the handlers that clients should call;
* avoid placing sensitive logic in public handler methods;
* validate permissions inside handlers for object-specific access;
* keep internal helper methods private.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       ALLOWED_HANDLERS = {
           "default",
           "send_message",
           "fetch_history",
       }

       def send_message(self, request, *args, **kwargs):
           return None

       def fetch_history(self, request, *args, **kwargs):
           return None

       def _internal_helper(self):
           return None

In this example, clients should be able to call ``send_message`` and
``fetch_history``, but not ``_internal_helper``.

Django permissions
------------------

The package supports Django permission checks on WebSocket views.

You can require that a user has any of a set of permissions, or all permissions
in a set.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ModerationWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
       ]

       all_permissions_required = [
           "chat.can_moderate",
       ]

       def default(self, request, *args, **kwargs):
           return None

Use view-level permissions for broad access control.

For object-level rules, such as whether a user can join a specific room or send
to a specific tenant channel, add explicit checks inside your handler methods.

See :doc:`permissions`.

Authentication recommendations
------------------------------

For authenticated WebSocket features:

* require users to authenticate before requesting a WebSocket token;
* use WebSocket tokens for connection setup;
* validate that the connected user can access the requested channel;
* avoid relying only on the channel name for authorisation;
* check object-level permissions inside handlers;
* avoid exposing sensitive information in channel names or messages.

If anonymous WebSocket access is allowed, treat all incoming messages as
untrusted and apply strict validation and rate limiting.

IAM security
------------

The AWS credentials used by this package should have the smallest practical set
of permissions.

Separate deployment permissions from runtime permissions where possible.

Deployment permissions may include creating or updating API Gateway resources.

Runtime permissions usually include permission to send messages to connected
WebSocket clients through the API Gateway Management API.

Production recommendations:

* avoid administrator credentials;
* prefer IAM roles for AWS-hosted environments;
* use separate credentials per environment;
* restrict resources to the required ARNs where possible;
* rotate IAM user credentials if IAM users are used;
* remove broad setup permissions after deployment if they are no longer needed.

See :doc:`aws_iam_setup`.

Cookie and subdomain security
-----------------------------

If your main Django site and WebSocket endpoint use different subdomains, review
your cookie configuration.

For example:

.. code-block:: text

   https://www.example.com
   wss://ws.example.com

You may need to configure:

* ``CSRF_TRUSTED_ORIGINS``;
* ``CSRF_COOKIE_DOMAIN``;
* ``SESSION_COOKIE_DOMAIN``;
* ``SESSION_COOKIE_SAMESITE``;
* ``CSRF_COOKIE_SAMESITE``.

Be careful not to scope cookies more broadly than necessary.

If you change the session cookie name or domain, clear old sessions where
appropriate.

Cleanup and stale sessions
--------------------------

WebSocket clients may disconnect unexpectedly.

A stale session can remain in the database if the disconnect event is missed or
if API Gateway reports that a connection has gone away when sending a message.

Schedule cleanup tasks for:

* disconnected WebSocket sessions;
* expired or used WebSocket tokens;
* old rate limit records.

See :doc:`cleanup`.

Operational logging
-------------------

In production, monitor:

* rejected connection attempts;
* token validation failures;
* token rate limit failures;
* connection rate limit failures;
* unexpected headers;
* invalid channel names;
* failed message sends;
* AWS ``GoneException`` responses;
* unusual reconnect patterns.

Use these signals to identify misconfigured clients, deployment issues, or abuse.

Error handling
--------------

Security-sensitive errors should not expose unnecessary implementation details to
clients.

For example, avoid returning detailed reasons that reveal whether:

* a token exists;
* a user exists;
* a handler exists but is forbidden;
* an internal resource exists;
* an API Gateway ID is valid.

Detailed information should be logged for administrators, while client responses
should remain generic.

Production checklist
--------------------

Before deploying to production, review this checklist.

WebSocket protection
~~~~~~~~~~~~~~~~~~~~

* WebSocket tokens are enabled for authenticated connections.
* Tokens are short-lived and single-use.
* Reconnecting clients request a fresh token before reconnecting.
* Token generation is rate limited.

Django configuration
~~~~~~~~~~~~~~~~~~~~

* ``DEBUG`` is disabled.
* ``ALLOWED_HOSTS`` is configured.
* ``CSRF_TRUSTED_ORIGINS`` is configured.
* Session and CSRF cookie settings are correct for your domains.
* Secrets are provided through environment variables or a secret manager.

AWS configuration
~~~~~~~~~~~~~~~~~

* IAM permissions are restricted.
* Production and development AWS resources are separated.
* API Gateway records are reviewed.
* Custom domain certificates are valid.
* DNS points to the expected API Gateway domain.

Application logic
~~~~~~~~~~~~~~~~~

* Incoming message payloads are validated.
* Handler names are restricted.
* Django permissions are configured where needed.
* Object-level access is checked inside handlers.
* Channel names are validated and do not expose sensitive information.
* Message sizes are kept within AWS limits.

Operations
~~~~~~~~~~

* Stale sessions are cleaned up.
* Expired tokens are cleaned up.
* Old rate limit records are cleaned up.
* Connection failures are monitored.
* Token failures are monitored.
* Message send failures are monitored.

Reporting vulnerabilities
-------------------------

If you discover a security vulnerability, please follow the project's security
reporting process.

See the repository's security policy for details.

Related pages
-------------

See also:

* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`permissions`;
* :doc:`aws_iam_setup`;
* :doc:`configuration`;
* :doc:`api_gateway_setup`;
* :doc:`cleanup`;
* :doc:`troubleshooting`.

