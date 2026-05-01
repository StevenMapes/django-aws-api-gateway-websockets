Concepts
========

This page explains the main concepts used by
Django-AWS-API-Gateway-WebSockets.

If you are new to the package, read this page after :doc:`quickstart` and before
setting up more advanced routing or security.

Overview
--------

Django-AWS-API-Gateway-WebSockets lets Django handle WebSocket events through
AWS API Gateway.

AWS API Gateway owns the persistent WebSocket connection. Django receives HTTP
requests from API Gateway when clients connect, disconnect, or send messages.

The package then helps Django:

* validate the API Gateway request;
* track WebSocket sessions;
* associate connections with users;
* group connections into channels;
* dispatch incoming messages to view methods;
* send messages back to connected clients;
* clean up stale connection data.

The important concepts are:

* API Gateway;
* WebSocket API;
* route;
* route key;
* route selection expression;
* target base endpoint;
* handler;
* action;
* channel;
* connection ID;
* WebSocket session;
* WebSocket token;
* unicast;
* multicast;
* broadcast.

API Gateway
-----------

AWS API Gateway is the AWS service that manages the WebSocket connection.

The browser connects to API Gateway using a WebSocket URL such as:

.. code-block:: text

   wss://ws.example.com

or an AWS-generated endpoint such as:

.. code-block:: text

   wss://abc123.execute-api.eu-west-1.amazonaws.com/production

Django does not hold the WebSocket connection open directly. API Gateway does.

When something happens on the connection, API Gateway calls your Django
application over HTTPS.

WebSocket API
-------------

A WebSocket API is the API Gateway resource that handles WebSocket connections.

It contains:

* routes;
* integrations;
* stages;
* optional custom domain mappings.

This package can create and configure those resources for you from Django Admin
or management commands.

See :doc:`api_gateway_setup`.

Route
-----

A route is an API Gateway concept.

Routes decide where API Gateway should send a WebSocket event.

The standard WebSocket routes are:

``$connect``
   Called when a client opens a WebSocket connection.

``$disconnect``
   Called when a client disconnects or the connection ends.

``$default``
   Called when no more specific route matches the incoming message.

You can also create custom routes.

For example:

.. code-block:: text

   chat_message
   notifications
   fetch_history

Route key
---------

The route key is the name of an API Gateway route.

Examples:

.. code-block:: text

   $connect
   $disconnect
   $default
   chat_message
   notifications

When API Gateway receives a WebSocket message, it uses the route selection
expression to decide which route key to use.

Route selection expression
--------------------------

The route selection expression tells API Gateway how to choose a route from an
incoming WebSocket message.

A common route selection expression is:

.. code-block:: text

   $request.body.action

This means API Gateway will inspect the JSON message body and use the value of
``action`` as the route key.

For example, this message:

.. code-block:: json

   {
     "action": "chat_message",
     "message": "Hello"
   }

would select the ``chat_message`` route if that route exists.

If no matching route exists, API Gateway can fall back to ``$default``.

Action
------

``action`` is a common JSON field used by API Gateway to select a route.

Example browser message:

.. code-block:: javascript

   socket.send(JSON.stringify({
       action: "chat_message",
       message: "Hello everyone"
   }));

In this example, ``chat_message`` is the action value.

If your API Gateway route selection expression is ``$request.body.action``, API
Gateway uses this value to decide which route should receive the message.

Handler
-------

A handler is a Django view method that processes an incoming WebSocket message.

For example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       def chat_message(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

In this example, ``chat_message`` is a handler method.

Depending on your configuration, Django may use an ``action`` or ``handler``
value from the incoming JSON body to choose the method to call.

Handler selection key
---------------------

The handler selection key is the JSON field used by Django to select a handler
method.

For example, the browser may send:

.. code-block:: json

   {
     "handler": "fetch_history"
   }

The view can then call the ``fetch_history`` method if that handler is allowed.

Route selection and handler selection are related but not always the same thing.

Route selection happens in API Gateway.

Handler selection happens in Django.

In simple projects, you may use the same value for both.

In larger projects, API Gateway may route messages to different Django views,
and each view may then perform its own handler selection.

Target base endpoint
--------------------

The target base endpoint is the Django URL that API Gateway calls, excluding the
final route slug.

For example, if your Django URL pattern is:

.. code-block:: python

   path(
       "ws/<slug:route>",
       ExampleWebSocketView.as_view(),
       name="example_websocket",
   )

and the public HTTPS URL is:

.. code-block:: text

   https://www.example.com/ws/<slug:route>

then the target base endpoint is:

.. code-block:: text

   https://www.example.com/ws/

The package appends the route name when creating API Gateway integrations.

The final API Gateway callback URLs become:

.. code-block:: text

   https://www.example.com/ws/connect
   https://www.example.com/ws/disconnect
   https://www.example.com/ws/default

For custom routes, the route name is appended in the same way.

Connection ID
-------------

API Gateway gives each WebSocket connection a connection ID.

The connection ID is used when Django sends a message back to a specific
connected client through the API Gateway Management API.

The package stores this value on the WebSocket session record.

WebSocket session
-----------------

A WebSocket session is a database record representing a WebSocket connection.

It stores information such as:

* API Gateway connection ID;
* channel name;
* associated Django user, where available;
* API Gateway record;
* whether the connection is currently active;
* request count;
* timestamps.

When a client connects, the package creates a WebSocket session.

When a client disconnects, the session is marked as disconnected.

Channel
-------

A channel is a string used to group WebSocket sessions.

For example:

.. code-block:: text

   general
   support
   tenant_123
   notifications_user_456

A browser chooses a channel using the ``channel`` query string parameter.

Example:

.. code-block:: text

   wss://ws.example.com?channel=general

Django can then send a message to all active sessions in that channel.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       channel_name="general",
   ).send_message(
       {
           "type": "chat_message",
           "message": "Hello general room.",
       }
   )

Channels are not authorization
------------------------------

A channel is only a grouping value.

Do not assume that a user is allowed to access a channel just because they
requested it.

For sensitive channels, validate access server-side.

For example, if a client connects to:

.. code-block:: text

   wss://ws.example.com?channel=admin

you should still check whether the user is allowed to receive admin messages.

See :doc:`permissions`.

WebSocket token
---------------

A WebSocket token is a short-lived, single-use token used to protect
authenticated WebSocket connections.

The normal flow is:

#. browser requests a token from Django using a CSRF-protected HTTP request;
#. Django creates a token linked to the user and session;
#. browser opens the WebSocket connection with the token;
#. Django validates and consumes the token during connection.

Example WebSocket URL:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Tokens should not be reused.

If the client reconnects, it should request a fresh token.

See :doc:`websocket_tokens`.

Unicast
-------

Unicast means sending a message to one specific WebSocket connection.

For example, inside a view you can send a reply to the current connection.

.. code-block:: python

   self.websocket_session.send_message(
       {
           "type": "reply",
           "message": "This message is only for this connection.",
       }
   )

Use unicast for:

* replies to a specific request;
* private notifications;
* validation errors;
* one user's task progress;
* acknowledgements.

Multicast
---------

Multicast means sending a message to multiple connections in a group.

In this package, multicast is usually done by filtering WebSocket sessions by
channel.

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       channel_name="support",
   ).send_message(
       {
           "type": "chat_message",
           "message": "Hello support room.",
       }
   )

Use multicast for:

* chat rooms;
* live dashboards;
* document collaboration;
* team notifications;
* tenant-specific updates.

Broadcast
---------

Broadcast means sending a message to all active WebSocket sessions.

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

Use broadcast carefully.

It is useful for:

* maintenance notices;
* system-wide announcements;
* global status messages.

Avoid broadcasting large or frequent messages unless you understand the
performance and cost implications.

API Gateway record
------------------

The API Gateway record is the Django model instance that stores the API Gateway
configuration.

It includes values such as:

* API name;
* target base endpoint;
* default channel name;
* route selection expression;
* stage name;
* custom domain name;
* certificate ARN;
* hosted zone ID;
* API ID returned by AWS;
* API endpoint returned by AWS;
* deployment state.

This record is used when creating AWS resources and when validating incoming
requests.

Additional route
----------------

An additional route maps a custom API Gateway route key to a target Django URL.

Additional routes are useful when different parts of your project should receive
different WebSocket messages.

For example:

.. code-block:: text

   notifications -> https://www.example.com/ws/notifications/
   chat          -> https://www.example.com/ws/chat/
   dashboard     -> https://www.example.com/ws/dashboard/

See :doc:`adding_new_routes`.

Stage
-----

An API Gateway stage is a deployed version of the API.

Common stage names include:

.. code-block:: text

   development
   staging
   production

This package currently uses the stage name configured on the API Gateway record.

Custom domain
-------------

A custom domain gives your WebSocket API a friendly URL.

For example:

.. code-block:: text

   wss://ws.example.com

Without a custom domain, clients use the generated AWS API Gateway URL.

Custom domains are recommended for production, but they are not required for
basic testing.

See :doc:`api_gateway_setup`.

Putting the concepts together
-----------------------------

A typical authenticated connection flow looks like this:

#. user opens a Django page;
#. page requests a WebSocket token;
#. browser opens ``wss://ws.example.com?ws_token=<token>&channel=general``;
#. API Gateway receives the connection;
#. API Gateway calls Django's ``connect`` route;
#. Django validates the token, API Gateway, headers, connection ID, and channel;
#. Django creates a WebSocket session;
#. browser sends ``{"action": "chat_message", "message": "Hello"}``;
#. API Gateway uses ``action`` to select a route;
#. Django uses the message to select a handler;
#. Django processes the message;
#. Django sends a message to one connection, one channel, or all connections.

Common confusion
----------------

Route vs handler
~~~~~~~~~~~~~~~~

A route is selected by API Gateway.

A handler is selected by Django.

They may have the same name, but they are not the same concept.

Action vs channel
~~~~~~~~~~~~~~~~~

``action`` usually describes what the message wants to do.

``channel`` describes which group the connection belongs to.

Example:

.. code-block:: json

   {
     "action": "send_message",
     "message": "Hello"
   }

The channel is usually in the URL:

.. code-block:: text

   wss://ws.example.com?channel=general

Connection vs session
~~~~~~~~~~~~~~~~~~~~~

The connection is the live WebSocket connection managed by API Gateway.

The session is the Django database record that stores information about that
connection.

WebSocket token vs CSRF token
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A CSRF token protects the HTTP request used to request a WebSocket token.

A WebSocket token protects the WebSocket connection itself.

Related pages
-------------

See also:

* :doc:`quickstart`;
* :doc:`api_gateway_setup`;
* :doc:`client_integration`;
* :doc:`websocket_tokens`;
* :doc:`permissions`;
* :doc:`adding_new_routes`;
* :doc:`example`;
* :doc:`architecture`.
