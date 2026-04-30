Models
======

This page explains the main database models used by
Django-AWS-API-Gateway-WebSockets.

The models are used to:

* store API Gateway configuration;
* track WebSocket connections;
* group connections into channels;
* map custom routes to Django endpoints;
* store short-lived WebSocket tokens;
* record connection rate limit attempts.

Overview
--------

The main models are:

``ApiGateway``
   Stores configuration and AWS deployment details for a WebSocket API Gateway.

``ApiGatewayAdditionalRoute``
   Stores additional custom route mappings for an API Gateway.

``WebSocketSession``
   Stores active and historical WebSocket connection records.

``WebSocketToken``
   Stores short-lived, single-use tokens used to protect WebSocket connections.

``ConnectionRateLimit``
   Stores connection attempts used by the rate limiting system.

These models are installed when you add the package to ``INSTALLED_APPS`` and
run migrations.

.. code-block:: console

   python manage.py migrate

ApiGateway
----------

``ApiGateway`` stores the configuration for an AWS API Gateway WebSocket API.

Each record represents one WebSocket API Gateway endpoint.

It is used when:

* creating the API Gateway in AWS;
* creating routes and integrations;
* creating API Gateway stages;
* creating custom domain mappings;
* validating incoming requests from API Gateway;
* sending messages back to connected clients.

Common fields
~~~~~~~~~~~~~

``api_name``
   A human-friendly name for the API Gateway.

``api_description``
   Optional description for the API Gateway.

``default_channel_name``
   The channel name used when a client connects without specifying a
   ``channel`` query string parameter.

``domain_name``
   The custom domain you want to use for the WebSocket endpoint, such as
   ``ws.example.com``.

``target_base_endpoint``
   The HTTPS URL on your Django site where API Gateway should send WebSocket
   route requests, excluding the final route slug.

   For example, if your Django URL is:

   .. code-block:: text

      https://www.example.com/ws/<slug:route>

   then the target base endpoint should be:

   .. code-block:: text

      https://www.example.com/ws/

``certificate_arn``
   The AWS Certificate Manager certificate ARN used for the custom domain.

``hosted_zone_id``
   The Route 53 hosted zone ID, if using Route 53.

``api_key_selection_expression``
   API Gateway API key selection expression.

``route_selection_expression``
   API Gateway route selection expression.

   A common value is:

   .. code-block:: text

      $request.body.action

``route_key``
   The default route key. In most cases this remains ``$default``.

``stage_name``
   The API Gateway stage name, such as ``production`` or ``development``.

``stage_description``
   Optional stage description.

``tags``
   JSON field for AWS resource tags.

AWS-populated fields
~~~~~~~~~~~~~~~~~~~~

Some fields are populated after AWS resources are created.

``api_id``
   The API Gateway API ID returned by AWS.

``api_endpoint``
   The generated API Gateway endpoint returned by AWS.

``api_gateway_domain_name``
   The AWS API Gateway domain name used when configuring DNS for a custom
   domain.

``api_mapping_id``
   The API mapping ID returned by AWS.

``deployment_id``
   The latest deployment ID returned by AWS.

``api_created``
   Indicates whether the API Gateway has been created.

``custom_domain_created``
   Indicates whether the custom domain mapping has been created.

Creating an API Gateway
~~~~~~~~~~~~~~~~~~~~~~~

You normally create an ``ApiGateway`` record through Django Admin.

After the record exists, create the AWS resources using the admin action or the
management command.

.. code-block:: console

   python manage.py createApiGateway --pk=1

Replace ``1`` with the primary key of the ``ApiGateway`` record.

Creating a custom domain
~~~~~~~~~~~~~~~~~~~~~~~~

After the API Gateway has been created, create the custom domain mapping.

.. code-block:: console

   python manage.py createCustomDomain --pk=1

Replace ``1`` with the primary key of the ``ApiGateway`` record.

See :doc:`api_gateway_setup`.

ApiGatewayAdditionalRoute
-------------------------

``ApiGatewayAdditionalRoute`` stores custom route mappings for an existing
``ApiGateway``.

Additional routes are useful when you want API Gateway to send different route
keys to different Django endpoints.

For example:

.. code-block:: text

   chat          -> https://www.example.com/ws/chat/
   notifications -> https://www.example.com/ws/notifications/
   dashboard     -> https://www.example.com/ws/dashboard/

Common fields
~~~~~~~~~~~~~

``api_gateway``
   The parent ``ApiGateway`` record.

``name``
   Human-friendly name for the route.

``route_key``
   The API Gateway route key.

   For example:

   .. code-block:: text

      chat_message
      notifications
      fetch_history

``integration_url``
   The target Django URL for this route.

``deployed``
   Indicates whether the route has been deployed to AWS.

Creating additional routes
~~~~~~~~~~~~~~~~~~~~~~~~~~

Additional routes can be managed through Django Admin or by creating model
records in your own deployment process.

If the parent API Gateway has already been deployed, creating an additional
route can deploy the new route to AWS.

If the parent API Gateway has not yet been deployed, additional routes are
created during the main API Gateway deployment.

See :doc:`adding_new_routes`.

WebSocketSession
----------------

``WebSocketSession`` stores information about WebSocket connections.

A record is created when a client connects. The record is marked disconnected
when the client disconnects.

Common fields
~~~~~~~~~~~~~

``connection_id``
   The API Gateway connection ID for the WebSocket connection.

``channel_name``
   The channel associated with the connection.

``user``
   The Django user associated with the connection, if available.

``connected``
   Indicates whether the session is currently considered connected.

``api_gateway``
   The ``ApiGateway`` record associated with this connection.

``request_count``
   Count of requests handled for the session.

``created_on``
   Timestamp when the session was created.

``updated_on``
   Timestamp when the session was last updated.

Channels
~~~~~~~~

Channels group WebSocket sessions.

Clients can choose a channel with the ``channel`` query string parameter:

.. code-block:: text

   wss://ws.example.com?channel=general

You can then send a message to all active sessions in that channel.

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

Channels should not be treated as authorization. Always check server-side
permissions before allowing access to sensitive channels.

Sending a message to one session
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A ``WebSocketSession`` can send a message to its own connection.

.. code-block:: python

   session.send_message(
       {
           "type": "notification",
           "message": "This message is only for this connection.",
       }
   )

Inside a ``WebSocketView``, the current session is available as
``self.websocket_session``.

.. code-block:: python

   self.websocket_session.send_message(
       {
           "type": "reply",
           "message": "Django received your message.",
       }
   )

Sending to multiple sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``WebSocketSession`` queryset supports sending the same message to all
connected sessions in the queryset.

Send to one channel:

.. code-block:: python

   WebSocketSession.objects.filter(
       channel_name="support",
   ).send_message(
       {
           "type": "support_message",
           "message": "Hello support room.",
       }
   )

Broadcast to all connected sessions:

.. code-block:: python

   WebSocketSession.objects.filter(
       connected=True,
   ).send_message(
       {
           "type": "system",
           "message": "Maintenance will begin in 5 minutes.",
       }
   )

Disconnected sessions
~~~~~~~~~~~~~~~~~~~~~

When a WebSocket disconnects, the session is marked as disconnected.

Old disconnected sessions should be cleaned up regularly.

.. code-block:: console

   python manage.py clearWebSocketSessions

See :doc:`cleanup`.

WebSocketToken
--------------

``WebSocketToken`` stores short-lived, single-use tokens used to protect
authenticated WebSocket connections.

The token flow is:

#. browser requests a token from Django using a CSRF-protected HTTP request;
#. Django creates a token linked to the user and session;
#. browser opens the WebSocket connection with the token;
#. Django validates and consumes the token during connection.

Common fields
~~~~~~~~~~~~~

``token``
   The generated token value.

``user``
   The Django user the token belongs to.

``session_key``
   The Django session key the token is bound to.

``created_at``
   Timestamp when the token was created.

``used``
   Indicates whether the token has already been consumed.

Token behaviour
~~~~~~~~~~~~~~~

Tokens are:

* short-lived;
* single-use;
* bound to a Django session;
* linked to an authenticated user.

A token should be requested immediately before opening the WebSocket connection.

Do not reuse tokens for reconnects.

See :doc:`websocket_tokens`.

Generating tokens
~~~~~~~~~~~~~~~~~

Most users should use the built-in token view rather than creating tokens
directly.

Add the token view to your URL configuration:

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

The browser then requests a token from that endpoint before connecting.

Cleaning up tokens
~~~~~~~~~~~~~~~~~~

Expired and used tokens should be cleaned up regularly.

.. code-block:: console

   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

See :doc:`cleanup`.

ConnectionRateLimit
-------------------

``ConnectionRateLimit`` stores connection attempts for rate limiting.

It is used to help protect WebSocket endpoints from excessive connection
attempts.

Common fields
~~~~~~~~~~~~~

``ip_address``
   The IP address associated with the connection attempt.

``user``
   The authenticated Django user, if available.

``attempt_time``
   Timestamp for the attempt.

``successful``
   Whether the connection attempt was successful.

Default limits
~~~~~~~~~~~~~~

By default, connection attempts are limited to:

.. code-block:: text

   20 attempts per 5 minutes

The limit is checked by IP address and by authenticated user when available.

Customising limits
~~~~~~~~~~~~~~~~~~

You can customise connection rate limits on your WebSocket view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 10
       RATE_LIMIT_WINDOW_MINUTES = 5

       def default(self, request, *args, **kwargs):
           return None

See :doc:`rate_limiting`.

Cleaning up rate limit records
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Old rate limit records should be cleaned up regularly.

.. code-block:: console

   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

Despite the command name, this command also cleans old rate limit records.

Model relationships
-------------------

The main relationships are:

.. code-block:: text

   ApiGateway
      |
      |-- ApiGatewayAdditionalRoute
      |
      |-- WebSocketSession

   WebSocketSession
      |
      |-- user
      |
      |-- api_gateway

   WebSocketToken
      |
      |-- user

   ConnectionRateLimit
      |
      |-- user

In practice:

* one ``ApiGateway`` can have many ``WebSocketSession`` records;
* one ``ApiGateway`` can have many ``ApiGatewayAdditionalRoute`` records;
* one user can have many WebSocket sessions;
* one user can have many WebSocket tokens;
* one user can have many rate limit attempt records.

Common queries
--------------

List active sessions
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession


   sessions = WebSocketSession.objects.filter(connected=True)

List active sessions in a channel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   sessions = WebSocketSession.objects.filter(
       connected=True,
       channel_name="general",
   )

List sessions for a user
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   sessions = request.user.websocket_sessions.filter(
       connected=True,
   )

Send a message to a user's active sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   request.user.websocket_sessions.filter(
       connected=True,
   ).send_message(
       {
           "type": "notification",
           "message": "This message was sent to all your active sessions.",
       }
   )

Find disconnected sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   sessions = WebSocketSession.objects.filter(
       connected=False,
   )

Operational notes
-----------------

Use cleanup commands
~~~~~~~~~~~~~~~~~~~~

WebSocket applications create short-lived operational records.

Schedule cleanup for:

* disconnected sessions;
* expired or used WebSocket tokens;
* old rate limit records.

See :doc:`cleanup`.

Handle stale connections
~~~~~~~~~~~~~~~~~~~~~~~~

A session can become stale if a browser closes unexpectedly or a network
connection drops.

When sending to stale connections, AWS may report that the connection has gone
away. Treat this as normal behaviour and ensure stale sessions are cleaned up.

Avoid storing sensitive channel names
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Channel names are stored in the database.

Avoid putting sensitive information directly in channel names.

Prefer safe identifiers such as:

.. code-block:: text

   room_123
   tenant_456
   notifications_user_789

instead of values such as email addresses or customer names.

Keep messages small
~~~~~~~~~~~~~~~~~~~

AWS API Gateway WebSocket messages have size limits.

Send compact JSON messages over WebSocket. For larger data, send a reference and
let the browser fetch the full data over HTTPS.

Related pages
-------------

See also:

* :doc:`api_gateway_setup`;
* :doc:`adding_new_routes`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`message_patterns`;
* :doc:`cleanup`;
* :doc:`admin`;
* :doc:`architecture`.
