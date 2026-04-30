Troubleshooting
===============

This page lists common problems when using
Django-AWS-API-Gateway-WebSockets and how to investigate them.

General checklist
-----------------

If something is not working, start with this checklist:

* the Django application is reachable over HTTPS;
* the API Gateway has been created and deployed;
* the API Gateway record in Django has the expected API ID;
* the target base endpoint is correct and ends with a trailing slash;
* the Django URL includes ``<slug:route>``;
* the slug parameter is named ``route``;
* AWS credentials are configured correctly;
* IAM permissions allow the action you are trying to perform;
* DNS points to the correct API Gateway domain;
* the browser is connecting with ``wss://``;
* WebSocket tokens are configured correctly if enabled;
* old sessions, tokens, and rate limit records are being cleaned up.

Connection fails immediately
----------------------------

Symptoms
~~~~~~~~

The browser cannot open the WebSocket connection.

You may see errors such as:

.. code-block:: text

   WebSocket connection failed

or:

.. code-block:: text

   Error during WebSocket handshake

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* incorrect WebSocket URL;
* using ``https://`` instead of ``wss://``;
* DNS not pointing to API Gateway;
* custom domain not configured correctly;
* certificate not valid;
* API Gateway stage not deployed;
* Django endpoint not reachable from API Gateway;
* missing or invalid WebSocket token;
* API Gateway routes not configured.

What to check
~~~~~~~~~~~~~

Check that the browser connects to a WebSocket URL:

.. code-block:: text

   wss://ws.example.com

not:

.. code-block:: text

   https://ws.example.com

Check that the custom domain resolves correctly.

Check that the API Gateway record has been created and deployed.

Check that API Gateway can reach your Django endpoint over HTTPS.

Django returns bad request
--------------------------

Symptoms
~~~~~~~~

The connection reaches Django, but Django rejects it with a bad request.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* missing expected headers;
* request did not come through API Gateway;
* invalid host or origin;
* invalid connection ID;
* invalid channel name;
* missing token;
* expired token;
* reused token;
* route parameter is missing or misnamed.

What to check
~~~~~~~~~~~~~

Confirm that your Django URL pattern contains a slug named ``route``.

.. code-block:: python

   path(
       "ws/<slug:route>",
       ExampleWebSocketView.as_view(),
       name="example_websocket",
   )

The parameter must be named ``route``.

If using a local tunnel or proxy, check whether expected headers are being
removed or rewritten.

Messages always go to the default handler
-----------------------------------------

Symptoms
~~~~~~~~

Custom handlers are not called. All messages are handled by ``default``.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* the client payload does not include the expected handler or action key;
* the API Gateway route selection expression does not match the payload;
* the Django view uses a different handler selection key;
* the custom handler is not included in allowed handlers;
* the method name does not match the requested handler name;
* the handler name contains characters that are not valid for a Python method.

What to check
~~~~~~~~~~~~~

Check the client payload.

.. code-block:: javascript

   socket.send(JSON.stringify({
       action: "chat_message",
       message: "Hello"
   }));

Check that the Django view has a matching method.

.. code-block:: python

   def chat_message(self, request, *args, **kwargs):
       return None

If using explicit handler whitelisting, check that the handler is allowed.

.. code-block:: python

   ALLOWED_HANDLERS = {
       "default",
       "chat_message",
   }

Custom route is not called
--------------------------

Symptoms
~~~~~~~~

A custom API Gateway route does not call the expected Django view.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* the custom route has not been created;
* the API Gateway has not been redeployed;
* the route key does not match the client payload;
* the additional route integration URL is wrong;
* the target Django URL is not reachable;
* the route selection expression does not match your message shape.

What to check
~~~~~~~~~~~~~

Confirm that the additional route exists in AWS API Gateway.

Confirm that the API Gateway stage has been redeployed.

Confirm that the client sends the expected route key.

.. code-block:: javascript

   socket.send(JSON.stringify({
       action: "notifications",
       message: "Hello"
   }));

Confirm that the route key is ``notifications`` if that is the route you expect.

WebSocket token request fails
-----------------------------

Symptoms
~~~~~~~~

The browser cannot get a WebSocket token.

The token endpoint may return ``403 Forbidden``.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* user is not authenticated;
* CSRF token is missing;
* CSRF token is invalid;
* session cookie is missing;
* token generation rate limit has been exceeded;
* token endpoint URL is wrong;
* cookies are not being sent with the request.

What to check
~~~~~~~~~~~~~

Make sure the request includes:

* ``X-CSRFToken`` header;
* Django session cookie;
* ``credentials: "same-origin"`` in the fetch request.

Example:

.. code-block:: javascript

   const response = await fetch("/api/ws-token/", {
       method: "POST",
       headers: {
           "X-CSRFToken": csrfToken,
           "Content-Type": "application/json"
       },
       credentials: "same-origin"
   });

See :doc:`websocket_tokens`.

WebSocket token is rejected during connection
--------------------------------------------

Symptoms
~~~~~~~~

The token request succeeds, but the WebSocket connection is rejected.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* token was not included in the WebSocket URL;
* token expired before the connection was opened;
* token was already used;
* reconnect attempted to reuse an old token;
* session cookie changed between token request and connection;
* connection is opened from a different browser context.

What to check
~~~~~~~~~~~~~

Check that the URL includes ``ws_token``.

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Request the token immediately before opening the WebSocket connection.

For reconnects, always request a fresh token.

Rate limit exceeded
-------------------

Symptoms
~~~~~~~~

Connections or token requests are rejected after repeated attempts.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* reconnect loop is too aggressive;
* frontend repeatedly requests tokens;
* multiple tabs are open;
* connection attempts are failing and retrying rapidly;
* legitimate usage exceeds the configured limits;
* abuse or automated traffic.

What to check
~~~~~~~~~~~~~

Check the reconnect settings in the browser.

Avoid rapid reconnect loops.

If using ``reconnecting-websocket``, use backoff settings.

.. code-block:: javascript

   const socket = new ReconnectingWebSocket(websocketUrl, null, {
       debug: false,
       reconnectInterval: 3000,
       maxReconnectInterval: 10000,
       reconnectDecay: 1.5,
       timeoutInterval: 5000,
       maxReconnectAttempts: null
   });

If legitimate clients are being limited, adjust the view settings.

.. code-block:: python

   class ExampleWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 40
       RATE_LIMIT_WINDOW_MINUTES = 5

See :doc:`rate_limiting`.

User is anonymous unexpectedly
------------------------------

Symptoms
~~~~~~~~

The WebSocket view receives an anonymous user when an authenticated user was
expected.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* WebSocket token protection is disabled;
* token request was made anonymously;
* session cookie is not available to the WebSocket endpoint;
* cookie domain does not cover the WebSocket subdomain;
* session expired;
* user logged out before connecting;
* custom domain setup uses a different parent domain.

What to check
~~~~~~~~~~~~~

If your site is:

.. code-block:: text

   https://www.example.com

and your WebSocket endpoint is:

.. code-block:: text

   wss://ws.example.com

review your cookie settings.

You may need to configure:

* ``SESSION_COOKIE_DOMAIN``;
* ``CSRF_COOKIE_DOMAIN``;
* ``CSRF_TRUSTED_ORIGINS``;
* ``SESSION_COOKIE_SAMESITE``;
* ``CSRF_COOKIE_SAMESITE``.

See :doc:`configuration` and :doc:`api_gateway_setup`.

Permission denied
-----------------

Symptoms
~~~~~~~~

The connection works, but a message handler returns permission denied.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* user does not have the required Django permission;
* view-level permissions are too strict;
* handler-level permission check fails;
* user is connected to a channel they cannot access;
* object-level access check fails.

What to check
~~~~~~~~~~~~~

Check the user's Django permissions.

Check the view configuration.

.. code-block:: python

   class ExampleWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
       ]

For object-level access, check your handler logic.

See :doc:`permissions`.

Messages are not received by the browser
----------------------------------------

Symptoms
~~~~~~~~

Django sends a message, but the browser does not receive it.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* the connection is no longer active;
* the message was sent to the wrong channel;
* the session has ``connected=False``;
* stale session records exist;
* AWS returned a gone connection response;
* the browser's ``onmessage`` handler has an error;
* the message is not valid JSON for your frontend handler;
* the user changed rooms and is now on another channel.

What to check
~~~~~~~~~~~~~

Check that the queryset targets the expected channel.

.. code-block:: python

   WebSocketSession.objects.filter(
       channel_name="general",
   ).send_message(
       {
           "type": "chat_message",
           "message": "Hello",
       }
   )

Check the browser console for JavaScript errors.

Check that stale sessions are being cleaned up.

See :doc:`cleanup`.

GoneException when sending messages
-----------------------------------

Symptoms
~~~~~~~~

AWS reports that a connection has gone away when Django tries to send a message.

Possible causes
~~~~~~~~~~~~~~~

This usually means the client is no longer connected.

Common causes include:

* browser tab was closed;
* network disconnected;
* API Gateway timed out the connection;
* client changed rooms;
* stale session still exists in the database.

What to check
~~~~~~~~~~~~~

Treat gone connections as normal operational behaviour.

Make sure cleanup is scheduled.

See :doc:`cleanup`.

Messages fail because they are too large
----------------------------------------

Symptoms
~~~~~~~~

Sending a message fails when the payload is large.

Possible causes
~~~~~~~~~~~~~~~

AWS API Gateway WebSocket messages have size limits.

What to check
~~~~~~~~~~~~~

Keep WebSocket messages small.

For large payloads, send a lightweight notification and let the browser fetch
the full data over HTTPS.

Example:

.. code-block:: json

   {
     "type": "report_ready",
     "report_id": 123,
     "fetch_url": "/reports/123/"
   }

Local development does not work
-------------------------------

Symptoms
~~~~~~~~

The application works in production but not locally, or API Gateway cannot reach
the local Django server.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* local server is not publicly reachable;
* local server is not using HTTPS;
* tunnel URL changed;
* API Gateway target endpoint still points to an old URL;
* tunnel strips or rewrites headers;
* Django ``ALLOWED_HOSTS`` does not include the tunnel host.

What to check
~~~~~~~~~~~~~

Use a tunnelling service to expose your local server over HTTPS.

Update the API Gateway target base endpoint to the tunnel URL.

Check ``ALLOWED_HOSTS`` and CSRF settings.

See :doc:`local_development`.

Custom domain does not work
---------------------------

Symptoms
~~~~~~~~

The generated API Gateway endpoint works, but the custom domain does not.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* certificate is not validated;
* certificate does not cover the WebSocket domain;
* DNS record points to the wrong target;
* API mapping was not created;
* custom domain is in the wrong AWS region;
* stage mapping is incorrect.

What to check
~~~~~~~~~~~~~

Check the API Gateway record for the API Gateway domain name.

Check your DNS provider.

Check the certificate in AWS Certificate Manager.

Check that the custom domain is mapped to the expected API and stage.

API Gateway creation fails
--------------------------

Symptoms
~~~~~~~~

The admin action or management command fails when creating API Gateway
resources.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* missing IAM permissions;
* incorrect AWS region;
* invalid target base endpoint;
* invalid certificate ARN;
* invalid domain name;
* AWS service-linked role permission issue;
* credentials are not available to Django.

What to check
~~~~~~~~~~~~~

Check AWS credentials.

Check the configured AWS region.

Check the IAM policy.

See :doc:`aws_iam_setup`.

Management command cannot send or create resources
--------------------------------------------------

Symptoms
~~~~~~~~

Management commands fail locally or in deployment.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* virtual environment is not active;
* Django settings module is not configured;
* AWS credentials are missing;
* wrong AWS profile is selected;
* IAM permissions are insufficient;
* command arguments are incorrect.

What to check
~~~~~~~~~~~~~

Check that you can run normal Django commands first.

Check the configured AWS credential method.

Check the primary key passed to API Gateway commands.

Example:

.. code-block:: console

   python manage.py createApiGateway --pk=1

Debugging WebSocket views
-------------------------

You can enable debug behaviour on the view during development.

Example:

.. code-block:: python

   path(
       "ws/<slug:route>",
       ExampleWebSocketView.as_view(debug=True),
       name="example_websocket",
   )

Do not expose detailed debugging information to users in production.

Cleanup problems
----------------

Symptoms
~~~~~~~~

The database contains many old sessions, tokens, or rate limit records.

Possible causes
~~~~~~~~~~~~~~~

Common causes include:

* cleanup commands are not scheduled;
* scheduled task is using the wrong environment;
* command name or arguments are wrong;
* task runner cannot access the Django project;
* stale sessions are expected but not being pruned.

What to check
~~~~~~~~~~~~~

Run cleanup manually first.

.. code-block:: console

   python manage.py clearWebSocketSessions
   python manage.py cleanWebSocketToken --token-age=300 --rate-limit-age=7

Then schedule the commands using cron, Celery Beat, a container scheduler, or
your platform's scheduled task system.

See :doc:`cleanup`.

Getting more information
------------------------

When debugging, collect:

* browser console errors;
* browser network WebSocket details;
* API Gateway logs;
* Django logs;
* API Gateway record values;
* WebSocket session records;
* token records;
* rate limit records;
* AWS region and account details;
* custom domain and DNS values.

Related pages
-------------

See also:

* :doc:`quickstart`;
* :doc:`configuration`;
* :doc:`api_gateway_setup`;
* :doc:`aws_iam_setup`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`permissions`;
* :doc:`cleanup`;
* :doc:`local_development`.
