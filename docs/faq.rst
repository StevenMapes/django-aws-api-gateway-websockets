FAQ
===

This page answers common questions about
Django-AWS-API-Gateway-WebSockets.

General
-------

Is this a replacement for Django Channels?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

No.

Django-AWS-API-Gateway-WebSockets is not intended to replace Django Channels.

Django Channels lets Django run an ASGI application that handles WebSocket
connections directly.

This package takes a different approach. AWS API Gateway owns the WebSocket
connection, and Django receives HTTP requests from API Gateway for connection,
message, and disconnection events.

Use this package when you want AWS API Gateway to handle the WebSocket
connection lifecycle and you want to write mostly normal Django class-based
views.

Why use AWS API Gateway for WebSockets?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AWS API Gateway can manage WebSocket connections for you.

This means your Django application does not need to run a long-lived WebSocket
server process.

Benefits can include:

* simpler Django deployment;
* API Gateway-managed WebSocket connections;
* server-to-client messaging through the API Gateway Management API;
* integration with AWS infrastructure;
* compatibility with traditional Django request/response views.

Do I need to run ASGI?
~~~~~~~~~~~~~~~~~~~~~~

No.

The package is designed around AWS API Gateway forwarding WebSocket events to
Django as HTTP requests.

Your Django application can handle those requests using class-based views.

Do I need a custom domain?
~~~~~~~~~~~~~~~~~~~~~~~~~~

No.

You can use the generated AWS API Gateway WebSocket endpoint.

A custom domain is recommended for production because it gives you a stable,
friendly URL such as:

.. code-block:: text

   wss://ws.example.com

without exposing the generated AWS endpoint to users.

Can I use this locally?
~~~~~~~~~~~~~~~~~~~~~~~

Yes, but AWS API Gateway must be able to reach your Django application over
HTTPS.

For local development, use a tunnelling tool such as ngrok, Cloudflare Tunnel,
or another HTTPS tunnel.

See :doc:`local_development`.

Installation and setup
----------------------

What are the basic setup steps?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The short version is:

#. install the package;
#. add it to ``INSTALLED_APPS``;
#. run migrations;
#. configure AWS credentials;
#. create a Django WebSocket view;
#. add a URL pattern with ``<slug:route>``;
#. create an API Gateway record;
#. create the AWS API Gateway resources;
#. connect from the browser.

See :doc:`quickstart`.

Why does my URL need ``<slug:route>``?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

API Gateway sends different WebSocket events for routes such as:

* ``$connect``;
* ``$disconnect``;
* ``$default``;
* custom routes.

The Django URL must include a slug named ``route`` so the package can determine
which route API Gateway is calling.

Example:

.. code-block:: python

   path(
       "ws/<slug:route>",
       ExampleWebSocketView.as_view(),
       name="example_websocket",
   )

The slug must be named ``route``.

What should the target base endpoint be?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The target base endpoint should be the full HTTPS URL to your Django WebSocket
path, excluding the route slug.

If your Django URL is:

.. code-block:: text

   https://www.example.com/ws/<slug:route>

then the target base endpoint should be:

.. code-block:: text

   https://www.example.com/ws/

The trailing slash is important.

What routes are created by default?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The package creates the standard API Gateway WebSocket routes:

* ``$connect``;
* ``$disconnect``;
* ``$default``.

You can add custom routes if your application needs them.

See :doc:`adding_new_routes`.

Connections and channels
------------------------

What is a WebSocket session?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A WebSocket session is a database record representing a WebSocket connection.

It stores information such as:

* API Gateway connection ID;
* channel name;
* connected state;
* associated user, where available;
* API Gateway record;
* timestamps.

What is a channel?
~~~~~~~~~~~~~~~~~~

A channel is a string used to group WebSocket sessions.

For example, you could use channels for:

* chat rooms;
* dashboards;
* notification streams;
* tenants;
* documents;
* users.

The browser selects a channel using the ``channel`` query string parameter.

Example:

.. code-block:: text

   wss://ws.example.com?channel=general

How do I change channel?
~~~~~~~~~~~~~~~~~~~~~~~~

A channel is selected when the WebSocket connection opens.

To change channel, close the current WebSocket connection and open a new one
with a different ``channel`` query string value.

Example:

.. code-block:: text

   wss://ws.example.com?channel=support

If WebSocket tokens are enabled, request a fresh token for the new connection.

Can users choose any channel?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Technically, the client can send any channel name in the query string.

Do not treat the channel name as proof of permission.

For sensitive channels, validate server-side that the user is allowed to join or
use the requested channel.

See :doc:`permissions`.

Messaging
---------

How do I send a message back to the current connection?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use the current WebSocket session from inside your view.

.. code-block:: python

   self.websocket_session.send_message(
       {
           "type": "reply",
           "message": "Hello from Django",
       }
   )

How do I send a message to everyone in a channel?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Filter ``WebSocketSession`` records by ``channel_name`` and call
``send_message`` on the queryset.

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession


   WebSocketSession.objects.filter(
       channel_name="general",
   ).send_message(
       {
           "type": "chat_message",
           "message": "Hello everyone in general.",
       }
   )

How do I send a message to all connected users?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Filter active sessions and call ``send_message``.

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession


   WebSocketSession.objects.filter(
       connected=True,
   ).send_message(
       {
           "type": "system",
           "message": "Maintenance will begin in 5 minutes.",
       }
   )

What happens if a connection is stale?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If AWS reports that a connection has gone away when sending a message, the
session can be marked disconnected.

You should also schedule cleanup for old sessions.

See :doc:`cleanup`.

Routing and handlers
--------------------

What is the difference between route, action, handler, and channel?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``route``
   The API Gateway route being called, such as ``$connect``, ``$disconnect``,
   ``$default``, or a custom route.

``action``
   A common JSON field used by API Gateway's route selection expression.

``handler``
   A Django-side value that can be used to select a handler method on the view.

``channel``
   A grouping value used to associate WebSocket sessions with a room, stream, or
   group.

See :doc:`concepts`.

Why are all messages going to the default handler?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Common reasons include:

* the client did not send the expected ``action`` or ``handler`` field;
* the route selection expression does not match the message body;
* the handler method name does not match the payload value;
* the handler is not allowed;
* the custom route has not been deployed.

See :doc:`troubleshooting`.

Can I add custom routes?
~~~~~~~~~~~~~~~~~~~~~~~~

Yes.

Custom routes can be added using the additional route model or through your own
deployment process.

See :doc:`adding_new_routes`.

Security
--------

Why is the WebSocket view CSRF exempt?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

API Gateway forwards WebSocket events to Django as HTTP requests. These requests
are not normal browser form submissions and do not carry CSRF tokens in the same
way Django expects for standard CSRF-protected views.

For authenticated WebSocket connections, the package provides WebSocket token
protection.

The token is requested through a normal CSRF-protected Django endpoint before the
WebSocket connection is opened.

See :doc:`websocket_tokens` and :doc:`security`.

What are WebSocket tokens?
~~~~~~~~~~~~~~~~~~~~~~~~~~

WebSocket tokens are short-lived, single-use tokens used to protect
authenticated WebSocket connections.

The browser requests a token over a CSRF-protected HTTP endpoint, then includes
the token in the WebSocket URL.

Example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Tokens should not be reused.

Do I need WebSocket tokens?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For authenticated WebSocket connections, yes, they are recommended.

For public anonymous endpoints, you may choose to disable token validation on a
specific view, but you should still use rate limiting and input validation.

How do I disable WebSocket tokens?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set ``USE_WS_TOKEN`` to ``False`` on a specific view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class PublicWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           return None

Only disable tokens when you understand the security implications.

How does rate limiting work?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Connection attempts are rate limited by IP address and, where available, by
authenticated user.

Token generation is also rate limited per user.

See :doc:`rate_limiting`.

Can I use Django permissions?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes.

You can configure a WebSocket view to require that a user has any permission in
a list, or all permissions in a list.

See :doc:`permissions`.

Deployment
----------

What AWS permissions are required?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The exact permissions depend on which features you use.

Common permissions include the ability to:

* create and manage API Gateway WebSocket APIs;
* create routes and integrations;
* deploy stages;
* create custom domains;
* send messages through the API Gateway Management API;
* read certificates;
* update DNS if using Route 53 automation.

See :doc:`aws_iam_setup`.

Should I use an IAM user or IAM role?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For production, prefer IAM roles.

Use IAM users only when roles are not available.

Avoid administrator credentials and restrict permissions where possible.

See :doc:`aws_iam_setup`.

Can I use multiple Django instances?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes.

AWS API Gateway owns the WebSocket connections, and session state is stored in
the database.

Multiple Django instances can handle callbacks as long as they share the same
database, settings, session configuration, and AWS access.

Do I need scheduled tasks?
~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, for production deployments you should schedule cleanup tasks.

Recommended cleanup includes:

* stale WebSocket sessions;
* expired or used WebSocket tokens;
* old rate limit records.

See :doc:`cleanup`.

Troubleshooting
---------------

Why do I get ``GoneException`` when sending messages?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This usually means the client is no longer connected.

Common causes include:

* the browser tab closed;
* the device lost network connectivity;
* API Gateway timed out the connection;
* the user changed channel;
* the database contains stale session records.

This is normal operational behaviour. Make sure stale sessions are cleaned up.

Why does the token work once and then fail?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

WebSocket tokens are single-use.

Request a new token for every new WebSocket connection, including reconnects and
channel changes.

Why does reconnecting fail with tokens enabled?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The reconnecting client may be trying to reuse the original token.

When token protection is enabled, reconnect logic must request a fresh token
before opening a new connection.

See :doc:`reconnecting_websocket`.

Why does local development fail?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AWS API Gateway must be able to reach your Django application over HTTPS.

Your local ``127.0.0.1`` address is not reachable from AWS.

Use a public HTTPS tunnel and update the API Gateway target base endpoint.

See :doc:`local_development`.

Where should I look for errors?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* browser console logs;
* browser network WebSocket details;
* Django logs;
* API Gateway logs;
* API Gateway route and integration configuration;
* WebSocket session records;
* token records;
* rate limit records;
* DNS and certificate configuration.

See :doc:`troubleshooting`.

Project
-------

How do I contribute?
~~~~~~~~~~~~~~~~~~~~

See :doc:`contributing`.

Where is the changelog?
~~~~~~~~~~~~~~~~~~~~~~~

See :doc:`changelog`.

Where can I report security issues?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Follow the project's security reporting process.

See the repository security policy and :doc:`security`.
