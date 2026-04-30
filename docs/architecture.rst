Architecture
============

Django-AWS-API-Gateway-WebSockets allows a Django application to handle AWS API
Gateway WebSocket events using normal Django views.

AWS API Gateway manages the persistent WebSocket connection. Django receives
HTTP requests from API Gateway for connection, disconnection, and message events.
The package records connection state in the database and allows Django to send
messages back to connected clients through the API Gateway Management API.

High-level architecture
-----------------------

The main components are:

* a browser or WebSocket client;
* AWS API Gateway WebSocket API;
* Django URL routing;
* ``WebSocketView`` subclasses;
* database models for API Gateway configuration, sessions, tokens, routes, and
  rate limiting;
* Boto3 clients for creating API Gateway resources and sending messages back to
  clients;
* Django Admin and management commands for setup and maintenance.

Architecture diagram
--------------------

The source diagram is shown below in Mermaid format.

If your Sphinx build supports Mermaid, this can be rendered as a diagram.
Otherwise, it remains useful as a readable text diagram.

.. code-block:: text

   graph TB
       subgraph "Client Side"
           WS[WebSocket Client Browser/App]
           PAGE[Web Page Django Template]
       end

       subgraph "AWS Infrastructure"
           APIGW[AWS API Gateway WebSocket API]

           subgraph "Routes"
               CONN[$connect Route]
               DISC[$disconnect Route]
               DEF[$default Route]
               CUST[Custom Routes]
           end
       end

       subgraph "Django Application"
           subgraph "URL Routing"
               URL[urls.py ws/<slug:route>]
               TOKEN_URL[urls.py api/ws-token/]
           end

           subgraph "Token Generation"
               TOKEN_VIEW[WebSocketTokenView]
               TOKEN_GEN[Generate single-use token]
           end

           subgraph "WebSocketView"
               DISPATCH[dispatch Method]
               SETUP[setup Method]

               subgraph "Security Checks"
                   RL[Rate Limiting]
                   HDR[Header Validation]
                   APIGW_CHK[API Gateway Check]
                   TOKEN_CHK[Token Validation]
                   CONN_ID[Connection ID Validation]
                   UA[User Agent Check]
                   PERM[Permission Check]
                   CHAN_VAL[Channel Name Validation]
               end

               subgraph "Handlers"
                   CONNECT[connect Handler]
                   DISCONNECT[disconnect Handler]
                   DEFAULT[default Handler]
                   CUSTOM[Custom Handlers]
               end
           end

           subgraph "Models"
               APIGW_MODEL[ApiGateway]
               WSS_MODEL[WebSocketSession]
               ROUTE_MODEL[ApiGatewayAdditionalRoute]
               TOKEN_MODEL[WebSocketToken]
               RATE_MODEL[ConnectionRateLimit]
           end

           subgraph "Admin and Management"
               ADMIN[Django Admin]
               CMD[Management Commands]
           end
       end

       subgraph "Messaging"
           SEND_UNI[Unicast]
           SEND_MULTI[Multicast]
           SEND_BROAD[Broadcast]
           BOTO3[Boto3 API Gateway Management API client]
       end

       PAGE --> TOKEN_URL
       TOKEN_URL --> TOKEN_VIEW
       TOKEN_VIEW --> TOKEN_GEN
       TOKEN_GEN --> TOKEN_MODEL
       PAGE --> WS
       WS --> APIGW
       APIGW --> CONN
       APIGW --> DISC
       APIGW --> DEF
       APIGW --> CUST
       CONN --> URL
       DISC --> URL
       DEF --> URL
       CUST --> URL
       URL --> DISPATCH
       DISPATCH --> SETUP
       SETUP --> RL
       RL --> RATE_MODEL
       RL --> HDR
       HDR --> APIGW_CHK
       APIGW_CHK --> TOKEN_CHK
       TOKEN_CHK --> TOKEN_MODEL
       TOKEN_CHK --> CONN_ID
       CONN_ID --> CHAN_VAL
       CHAN_VAL --> CONNECT
       CONNECT --> WSS_MODEL
       DISPATCH --> UA
       UA --> PERM
       PERM --> CUSTOM
       CUSTOM --> SEND_UNI
       CUSTOM --> SEND_MULTI
       CUSTOM --> SEND_BROAD
       SEND_UNI --> BOTO3
       SEND_MULTI --> BOTO3
       SEND_BROAD --> BOTO3
       BOTO3 --> APIGW
       APIGW --> WS
       DISCONNECT --> WSS_MODEL
       ADMIN --> APIGW_MODEL
       CMD --> APIGW_MODEL
       CMD --> TOKEN_MODEL
       CMD --> RATE_MODEL
       ROUTE_MODEL --> APIGW_MODEL
       APIGW_MODEL --> WSS_MODEL

Core request flow
-----------------

The package uses AWS API Gateway as the WebSocket server and Django as the
application handler.

The core flow is:

#. The browser opens a WebSocket connection to AWS API Gateway.
#. API Gateway sends an HTTP request to Django for the ``$connect`` route.
#. Django validates the request.
#. Django creates a ``WebSocketSession`` record.
#. The browser sends a WebSocket message.
#. API Gateway routes the message to Django.
#. Django dispatches the request to the appropriate view method.
#. Django can send a message back through the API Gateway Management API.
#. When the client disconnects, API Gateway calls Django again.
#. Django marks the session as disconnected.

Django URL routing
------------------

API Gateway forwards events to Django URL patterns.

The URL pattern must include a slug named ``route``. This allows API Gateway to
pass the route name to Django.

For example:

.. code-block:: python

   from django.urls import path

   from .views import ExampleWebSocketView


   urlpatterns = [
       path(
           "ws/<slug:route>",
           ExampleWebSocketView.as_view(),
           name="example_websocket",
       ),
   ]

Typical route values include:

* ``connect``;
* ``disconnect``;
* ``default``;
* custom route names.

AWS API Gateway routes
----------------------

The package creates the standard WebSocket routes:

* ``$connect``;
* ``$disconnect``;
* ``$default``.

Additional routes can also be created.

API Gateway uses its route selection expression to decide which route should
receive a message. The common default is to use the ``action`` field in the JSON
message body.

For example:

.. code-block:: json

   {
     "action": "chat_message",
     "message": "Hello"
   }

Django can then dispatch this to a matching handler method.

WebSocketView
-------------

``WebSocketView`` is the base class used to receive WebSocket events from API
Gateway.

It is responsible for:

* parsing the request body;
* validating expected headers;
* validating the API Gateway source;
* handling connection events;
* handling disconnection events;
* loading the current ``WebSocketSession``;
* selecting the appropriate handler method;
* checking permissions;
* applying connection rate limiting;
* validating WebSocket tokens when enabled.

The view follows Django's class-based view pattern, so application code can be
implemented by subclassing ``WebSocketView``.

Connection flow
---------------

When a client connects, API Gateway calls the Django endpoint for the
``$connect`` route.

During connection, the package performs several checks before creating the
session.

These include:

* connection rate limiting;
* required header checks;
* allowed host and origin checks;
* API Gateway validation;
* optional WebSocket token validation;
* connection ID validation;
* channel name validation.

If the checks pass, a ``WebSocketSession`` record is created.

The session stores information such as:

* the API Gateway connection ID;
* the channel name;
* the associated Django user, where available;
* the API Gateway configuration;
* whether the connection is active;
* request count;
* created and updated timestamps.

Message handling flow
---------------------

When a connected client sends a message, API Gateway forwards it to Django.

The package then:

#. parses the request body as JSON;
#. loads the matching ``WebSocketSession``;
#. checks the user agent;
#. validates the selected handler;
#. checks permissions where configured;
#. calls the selected handler method;
#. returns a Django response to API Gateway.

Handlers can be selected using either the newer handler selection key or the
legacy route selection key, depending on the configuration in your view.

A simple message might look like this:

.. code-block:: json

   {
     "action": "default",
     "message": "Hello from the browser"
   }

Or, using a custom handler:

.. code-block:: json

   {
     "handler": "chat_message",
     "message": "Hello from the browser"
   }

Disconnection flow
------------------

When the client disconnects or the connection times out, API Gateway sends a
``$disconnect`` event to Django.

The package marks the matching ``WebSocketSession`` as disconnected by setting
``connected`` to ``False``.

Disconnected sessions may be retained for audit or debugging purposes, but old
records should be cleaned up regularly.

See :doc:`cleanup`.

Security architecture
---------------------

The project uses several layers of protection.

Token generation
~~~~~~~~~~~~~~~~

When WebSocket token protection is enabled, clients must request a short-lived
token before opening a WebSocket connection.

The token is:

* tied to the authenticated Django user;
* tied to the Django session key;
* valid for a short period;
* single-use;
* consumed atomically when the WebSocket connection is established.

This helps protect authenticated WebSocket connections from cross-site request
forgery-style attacks.

Rate limiting
~~~~~~~~~~~~~

Connection attempts are rate limited by IP address and, where available, by
authenticated user.

Token generation is also rate limited per user.

The default connection rate limit is:

.. code-block:: text

   20 connection attempts per 5 minutes

The default token generation limit is:

.. code-block:: text

   10 tokens per user per minute

See :doc:`rate_limiting`.

Input validation
~~~~~~~~~~~~~~~~

The project validates several inputs, including:

* request body size;
* JSON request bodies;
* connection IDs;
* channel names;
* IP addresses;
* message size before sending to API Gateway.

This reduces the risk of malformed requests, unexpected payloads, and oversized
messages.

Header validation
~~~~~~~~~~~~~~~~~

The package checks for the headers expected from API Gateway.

These checks help confirm that the request has the structure expected from AWS
API Gateway rather than from a direct browser or arbitrary HTTP client.

API Gateway validation
~~~~~~~~~~~~~~~~~~~~~~

Incoming requests are checked against the configured API Gateway records in the
database.

A view can also be restricted to a specific API Gateway ID.

Permission checks
~~~~~~~~~~~~~~~~~

Django permissions can be used to restrict access to WebSocket handlers.

A view can require that the user has any of a set of permissions, or all of a
set of permissions.

For example:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ModerationWebSocketView(WebSocketView):
       permissions_required = ["chat.can_use_chat"]
       all_permissions_required = ["chat.can_moderate"]

       def default(self, request, *args, **kwargs):
           return None

Handler whitelisting
~~~~~~~~~~~~~~~~~~~~

The package avoids arbitrary method invocation by checking that requested handler
names are allowed.

This prevents clients from calling private or unintended methods on the view.

Messaging patterns
------------------

The package supports three common messaging patterns.

Unicast
~~~~~~~

Unicast sends a message to one specific WebSocket connection.

.. code-block:: python

   self.websocket_session.send_message(
       {
           "type": "notification",
           "message": "This message is only for you.",
       }
   )

Multicast
~~~~~~~~~

Multicast sends a message to all connected sessions in a specific channel.

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

Broadcast
~~~~~~~~~

Broadcast sends a message to all connected sessions.

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

Database models
---------------

ApiGateway
~~~~~~~~~~

Stores the API Gateway configuration and deployment details.

This includes:

* API name;
* target base endpoint;
* route selection expression;
* stage name;
* custom domain details;
* API ID returned by AWS;
* API endpoint returned by AWS;
* deployment state.

ApiGatewayAdditionalRoute
~~~~~~~~~~~~~~~~~~~~~~~~~

Stores custom route mappings for an API Gateway.

Additional routes allow different route keys to target different Django
endpoints.

WebSocketSession
~~~~~~~~~~~~~~~~

Stores active and historical WebSocket connection records.

It tracks:

* connection ID;
* channel name;
* user;
* connected state;
* API Gateway;
* request count;
* timestamps.

WebSocketToken
~~~~~~~~~~~~~~

Stores short-lived, single-use tokens used for WebSocket connection protection.

It tracks:

* token value;
* user;
* session key;
* creation time;
* whether the token has been used.

ConnectionRateLimit
~~~~~~~~~~~~~~~~~~~

Stores connection attempt records used by the rate limiting system.

It tracks:

* IP address;
* user, where available;
* attempt time;
* whether the attempt was successful.

Admin and management commands
-----------------------------

The package includes Django Admin integration and management commands for common
operational tasks.

Django Admin can be used to:

* configure API Gateway records;
* create API Gateway resources;
* create custom domain mappings;
* manage additional routes;
* inspect WebSocket sessions;
* inspect tokens and rate limit records.

Management commands can be used to:

* create API Gateway resources;
* create custom domain mappings;
* clear old WebSocket sessions;
* clean up old WebSocket tokens;
* clean up old rate limit records.

See :doc:`management_commands/index`.

Operational considerations
--------------------------

Production deployments should include scheduled cleanup.

Recommended cleanup tasks include:

* clearing stale WebSocket sessions;
* deleting expired WebSocket tokens;
* deleting old rate limit records.

You should also monitor:

* failed connection attempts;
* rejected token requests;
* WebSocket disconnect frequency;
* stale session count;
* API Gateway errors;
* message send failures;
* ``GoneException`` responses from AWS.

Read more in :doc:`cleanup`.

Configuration example
---------------------

A typical custom WebSocket view might configure token protection, rate limiting,
allowed handlers, and permissions.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class MyWebSocketView(WebSocketView):
       USE_WS_TOKEN = True

       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 20
       RATE_LIMIT_WINDOW_MINUTES = 5

       ALLOWED_HANDLERS = {
           "default",
           "chat_message",
           "fetch_history",
       }

       permissions_required = [
           "chat.can_use_chat",
       ]

       MAX_BODY_SIZE = 1024 * 128
       MAX_CHANNEL_NAME_LENGTH = 191

       def default(self, request, *args, **kwargs):
           return None

       def chat_message(self, request, *args, **kwargs):
           return None

       def fetch_history(self, request, *args, **kwargs):
           return None

Related pages
-------------

See also:

* :doc:`api_gateway_setup`;
* :doc:`configuration`;
* :doc:`rate_limiting`;
* :doc:`reconnecting_websocket`;
* :doc:`cleanup`;
* :doc:`adding_new_routes`;
* :doc:`management_commands/index`.
