Local development
=================

This guide explains how to work with Django-AWS-API-Gateway-WebSockets during
local development.

Because AWS API Gateway needs to call your Django application over HTTPS, local
development usually requires a public tunnel to your local Django server.

Overview
--------

In production, the request flow is usually:

.. code-block:: text

   Browser
      |
      | wss://ws.example.com
      v
   AWS API Gateway
      |
      | HTTPS request
      v
   https://www.example.com/ws/<route>

During local development, your Django application is normally running on:

.. code-block:: text

   http://127.0.0.1:8000

AWS API Gateway cannot call that private local address directly.

To test locally, expose your local server through a temporary HTTPS URL using a
tunnelling tool.

Common local setup
------------------

A common local development setup is:

.. code-block:: text

   Browser
      |
      | wss://your-api-gateway-domain
      v
   AWS API Gateway
      |
      | HTTPS callback request
      v
   https://temporary-tunnel.example/ws/<route>
      |
      v
   http://127.0.0.1:8000/ws/<route>

You can use tools such as:

* ngrok;
* Cloudflare Tunnel;
* localtunnel;
* another HTTPS tunnelling or reverse proxy service.

The exact tunnelling tool is up to you.

Basic local development steps
-----------------------------

#. Start your Django development server.
#. Start an HTTPS tunnel to your local server.
#. Update the API Gateway target base endpoint to the tunnel URL.
#. Make sure Django allows the tunnel host.
#. Create or redeploy the API Gateway routes.
#. Connect from the browser using the API Gateway WebSocket URL.
#. Watch Django logs while testing.

Start Django locally
--------------------

Run the Django development server.

.. code-block:: console

   python manage.py runserver 127.0.0.1:8000

Your local Django endpoint may be:

.. code-block:: text

   http://127.0.0.1:8000/ws/<route>

Start a tunnel
--------------

Start your tunnelling tool and point it at your local Django server.

For example, a tunnel might give you a public HTTPS URL such as:

.. code-block:: text

   https://example-tunnel.ngrok-free.app

or:

.. code-block:: text

   https://example.trycloudflare.com

Your Django WebSocket callback endpoint would then be:

.. code-block:: text

   https://example-tunnel.ngrok-free.app/ws/<route>

Update the API Gateway target endpoint
--------------------------------------

In the Django API Gateway record, set the target base endpoint to the public
tunnel URL plus your WebSocket path, excluding the final route slug.

For example, if your Django URL pattern is:

.. code-block:: python

   path(
       "ws/<slug:route>",
       ExampleWebSocketView.as_view(),
       name="example_websocket",
   )

and your tunnel URL is:

.. code-block:: text

   https://example-tunnel.ngrok-free.app

then the target base endpoint should be:

.. code-block:: text

   https://example-tunnel.ngrok-free.app/ws/

The trailing slash is important.

The route portion is appended by the package when creating API Gateway
integrations.

Allow the tunnel host in Django
-------------------------------

Add the tunnel host to ``ALLOWED_HOSTS`` while developing.

Example:

.. code-block:: python

   ALLOWED_HOSTS = [
       "127.0.0.1",
       "localhost",
       "example-tunnel.ngrok-free.app",
   ]

If your tunnel URL changes, update ``ALLOWED_HOSTS`` again.

CSRF trusted origins
--------------------

If you request WebSocket tokens from a page served through the tunnel, add the
tunnel origin to ``CSRF_TRUSTED_ORIGINS``.

Example:

.. code-block:: python

   CSRF_TRUSTED_ORIGINS = [
       "https://example-tunnel.ngrok-free.app",
   ]

If your normal web page is served from ``localhost`` but token requests go
through another host, review your cookie and CSRF setup carefully.

Local AWS credentials
---------------------

For local development, a named AWS profile is often convenient.

Example:

.. code-block:: python

   AWS_IAM_PROFILE = "default"

If your profile does not include a default region, set:

.. code-block:: python

   AWS_GATEWAY_REGION_NAME = "eu-west-1"

You can also use environment variables or explicit settings, but avoid committing
real credentials to source control.

See :doc:`configuration` and :doc:`aws_iam_setup`.

Create a local API Gateway record
---------------------------------

It is usually safest to create a separate API Gateway record for local
development.

For example:

.. list-table::
   :header-rows: 1

   * - Field
     - Example value
   * - API name
     - Local WebSocket API
   * - Default channel name
     - local
   * - Target base endpoint
     - https://example-tunnel.ngrok-free.app/ws/
   * - Stage name
     - development
   * - Route selection expression
     - $request.body.action

Avoid reusing the same API Gateway record for local development and production.

Create or update the API Gateway
--------------------------------

If this is a new local API Gateway record, create the AWS resources.

Using Django Admin:

#. create the API Gateway record;
#. select it in the list page;
#. run the ``Create API Gateway`` action.

Using a management command:

.. code-block:: console

   python manage.py createApiGateway --pk=1

Replace ``1`` with the primary key of the local API Gateway record.

If your tunnel URL changes
--------------------------

Many tunnel services create a new URL each time they start.

If your tunnel URL changes:

#. update the API Gateway target base endpoint;
#. update ``ALLOWED_HOSTS``;
#. update ``CSRF_TRUSTED_ORIGINS`` if needed;
#. recreate or update API Gateway integrations;
#. redeploy the API Gateway stage if needed.

If messages still go to the old tunnel URL, check the API Gateway integration
URLs in AWS.

Connecting from the browser
---------------------------

The browser still connects to the API Gateway WebSocket URL, not directly to the
tunnel URL.

Example:

.. code-block:: javascript

   const socket = new WebSocket("wss://your-api-gateway-id.execute-api.eu-west-1.amazonaws.com/development?channel=local");

If you have configured a local custom domain, use that instead.

The tunnel URL is used by API Gateway to call Django.

Testing without WebSocket tokens
--------------------------------

For a first local test, you may choose to disable WebSocket token validation on a
development-only view.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class LocalWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           return None

Only do this for local or low-risk anonymous testing.

For authenticated testing, use WebSocket tokens so local behaviour matches
production more closely.

Testing with WebSocket tokens
-----------------------------

If WebSocket tokens are enabled:

#. load a Django page as an authenticated user;
#. request a WebSocket token from the token endpoint;
#. immediately open the WebSocket connection with the token;
#. request a fresh token for each reconnect.

Example WebSocket URL:

.. code-block:: text

   wss://your-api-gateway-domain?ws_token=<token>&channel=local

If the token request fails locally, check:

* the user is authenticated;
* the CSRF token is being sent;
* the session cookie is being sent;
* ``CSRF_TRUSTED_ORIGINS`` includes the correct origin;
* the token endpoint URL is correct.

Debugging local requests
------------------------

Enable debug behaviour on your view while developing.

.. code-block:: python

   path(
       "ws/<slug:route>",
       ExampleWebSocketView.as_view(debug=True),
       name="example_websocket",
   )

Use Django logs to inspect what happens when API Gateway calls your local
endpoint.

Do not enable verbose debug output in production.

Header differences with tunnels
-------------------------------

Some tunnels, proxies, or local reverse proxy setups may remove or alter headers.

If Django rejects a request because expected headers are missing, compare:

* the headers API Gateway sends;
* the headers received by the tunnel;
* the headers received by Django.

For local development only, you may need to adjust view settings if a tunnel
does not preserve all expected headers.

Do not weaken header checks in production unless you understand the security
impact.

Common local issues
-------------------

API Gateway still calls the old tunnel URL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check the API Gateway integration URLs in AWS.

If your tunnel URL changed, update the API Gateway target base endpoint and
redeploy the API Gateway stage.

Django rejects the host
~~~~~~~~~~~~~~~~~~~~~~~

Add the tunnel hostname to ``ALLOWED_HOSTS``.

Example:

.. code-block:: python

   ALLOWED_HOSTS = [
       "localhost",
       "127.0.0.1",
       "example-tunnel.ngrok-free.app",
   ]

CSRF token request fails
~~~~~~~~~~~~~~~~~~~~~~~~

Add the tunnel origin to ``CSRF_TRUSTED_ORIGINS``.

Example:

.. code-block:: python

   CSRF_TRUSTED_ORIGINS = [
       "https://example-tunnel.ngrok-free.app",
   ]

Also check that the browser sends cookies with the request.

Connection opens but messages do not reach Django
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check:

* API Gateway route selection expression;
* client message payload;
* route key;
* deployed stage;
* target integration URL;
* Django URL pattern;
* tunnel request logs.

Messages always use the default handler
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that the message contains the expected action or handler value.

Example:

.. code-block:: javascript

   socket.send(JSON.stringify({
       action: "chat_message",
       message: "Hello"
   }));

Then check that your Django view has a matching method.

.. code-block:: python

   def chat_message(self, request, *args, **kwargs):
       return None

Rate limit exceeded during testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reconnect loops can quickly hit local rate limits.

You can temporarily relax limits on a local-only view.

.. code-block:: python

   class LocalWebSocketView(WebSocketView):
       RATE_LIMIT_ENABLED = True
       RATE_LIMIT_MAX_ATTEMPTS = 100
       RATE_LIMIT_WINDOW_MINUTES = 5

Do not copy overly permissive development limits into production.

Recommended local workflow
--------------------------

A practical workflow is:

#. start Django;
#. start your tunnel;
#. update local settings with the tunnel host;
#. update the local API Gateway record;
#. create or redeploy the API Gateway routes;
#. open the browser console;
#. connect to the API Gateway WebSocket URL;
#. send a simple ``default`` message;
#. confirm Django receives the request;
#. confirm Django can send a message back;
#. test reconnect behaviour;
#. test cleanup commands.

Local cleanup
-------------

Local testing can create many sessions, tokens, and rate limit records.

Run cleanup commands regularly.

.. code-block:: console

   python manage.py clearWebSocketSessions
   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

You can also clear local test data directly through Django Admin if appropriate.

Security reminders
------------------

For local development:

* keep production and local API Gateway records separate;
* do not commit AWS credentials;
* do not commit temporary tunnel URLs;
* do not weaken production security settings for local testing;
* do not reuse production API Gateway resources for experiments;
* keep WebSocket tokens enabled when testing authenticated flows;
* remove temporary local routes and records when no longer needed.

Related pages
-------------

See also:

* :doc:`quickstart`;
* :doc:`api_gateway_setup`;
* :doc:`configuration`;
* :doc:`websocket_tokens`;
* :doc:`reconnecting_websocket`;
* :doc:`rate_limiting`;
* :doc:`troubleshooting`;
* :doc:`cleanup`.
