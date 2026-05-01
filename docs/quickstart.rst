Quickstart
==========

This guide shows the shortest path to getting a Django view receiving WebSocket
messages through AWS API Gateway.

By the end of this guide you will have:

* installed the package;
* added it to your Django project;
* configured AWS access;
* created a WebSocket view;
* added a URL route for API Gateway;
* created the API Gateway resources;
* connected from a browser;
* sent a message to Django;
* sent a message back to the browser.

Before you start
----------------

You need:

* an existing Django project;
* access to an AWS account;
* AWS credentials or an IAM role with suitable permissions;
* a publicly reachable HTTPS endpoint for your Django application;
* an AWS Certificate Manager certificate if you want to use a custom WebSocket
  domain.

For local development, you can use a tunnelling service to expose your Django
site temporarily. See :doc:`local_development`.

For IAM permissions, see :doc:`aws_iam_setup`.

Install the package
-------------------

Install the package into your Django environment.

.. code-block:: console

   pip install django-aws-api-gateway-websockets

Add the app
-----------

Add the package to ``INSTALLED_APPS``.

.. code-block:: python

   INSTALLED_APPS = [
       # ...
       "django_aws_api_gateway_websockets",
   ]

Run migrations
--------------

Apply the database migrations.

.. code-block:: console

   python manage.py migrate

Configure AWS access
--------------------

The package uses Boto3 to create API Gateway resources and send messages back to
connected clients.

Choose one of the supported AWS credential approaches.

IAM role or instance profile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If your application runs on AWS with an IAM role attached, configure the AWS
region.

.. code-block:: python

   AWS_GATEWAY_REGION_NAME = "eu-west-1"

Named AWS profile
~~~~~~~~~~~~~~~~~

For local development with a named AWS profile, set:

.. code-block:: python

   AWS_IAM_PROFILE = "example"

Explicit AWS access key
~~~~~~~~~~~~~~~~~~~~~~~

You can also configure explicit credentials.

.. code-block:: python

   AWS_ACCESS_KEY_ID = "your-access-key"
   AWS_SECRET_ACCESS_KEY = "your-secret-key"
   AWS_GATEWAY_REGION_NAME = "eu-west-1"

Do not commit real credentials to source control. Use environment variables,
your platform's secret manager, or another secure secret management approach.

Create a WebSocket view
-----------------------

Create a Django view by subclassing ``WebSocketView``.

This example handles a simple message and sends a response back to the current
WebSocket connection.

.. code-block:: python

   # example/views.py

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ExampleWebSocketView(WebSocketView):
       USE_WS_TOKEN = False

       def default(self, request, *args, **kwargs):
           message = self.body.get("message", "")

           self.websocket_session.send_message(
               {
                   "type": "reply",
                   "message": f"Django received: {message}",
               }
           )

           return JsonResponse({"ok": True})

This quickstart disables WebSocket token validation to keep the first example
short. For production, use WebSocket tokens. See :doc:`websocket_tokens`.

Add the URL route
-----------------

Add a URL pattern for API Gateway to call.

The slug parameter must be named ``route``.

.. code-block:: python

   # example/urls.py

   from django.urls import path

   from .views import ExampleWebSocketView

   urlpatterns = [
       path(
           "ws/<slug:route>",
           ExampleWebSocketView.as_view(),
           name="example_websocket",
       ),
   ]

Include this URL configuration from your project URLs if required.

.. code-block:: python

   # project/urls.py

   from django.urls import include
   from django.urls import path

   urlpatterns = [
       path("", include("example.urls")),
   ]

The URL that API Gateway calls will look like:

.. code-block:: text

   https://www.example.com/ws/connect
   https://www.example.com/ws/default
   https://www.example.com/ws/disconnect

When configuring the API Gateway record, the target base endpoint should exclude
the route part.

For example:

.. code-block:: text

   https://www.example.com/ws/

Create an API Gateway record
----------------------------

Open Django Admin and create an API Gateway record.

Use values similar to the following:

.. list-table::
   :header-rows: 1

   * - Field
     - Example value
   * - API name
     - Example WebSocket API
   * - API description
     - Quickstart WebSocket API
   * - Default channel name
     - quickstart
   * - Domain name
     - ws.example.com
   * - Target base endpoint
     - https://www.example.com/ws/
   * - Certificate ARN
     - arn:aws:acm:eu-west-1:123456789012:certificate/example
   * - Hosted Zone ID
     - Your Route 53 hosted zone ID, if using Route 53
   * - Route selection expression
     - $request.body.action
   * - Route key
     - $default
   * - Stage name
     - production

If you are not using a custom domain yet, you can leave the domain-related
fields blank and use the generated API Gateway endpoint.

Create the API Gateway in AWS
-----------------------------

From Django Admin:

#. Open the API Gateway list page.
#. Select the API Gateway record.
#. Choose the ``Create API Gateway`` action.
#. Click ``Go``.

When the action completes, the record should contain an AWS API ID and API
endpoint.

If you do not use Django Admin, run the management command instead:

.. code-block:: console

   python manage.py createApiGateway --pk=1

Replace ``1`` with the primary key of your API Gateway record.

Create the custom domain
------------------------

If you configured a custom domain and certificate, create the custom domain
mapping.

From Django Admin:

#. Open the API Gateway list page.
#. Select the API Gateway record.
#. Choose the ``Create Custom Domain record for the API`` action.
#. Click ``Go``.

Or use the management command:

.. code-block:: console

   python manage.py createCustomDomain --pk=1

Replace ``1`` with the primary key of your API Gateway record.

Configure DNS
-------------

If using a custom domain such as:

.. code-block:: text

   ws.example.com

create a DNS record pointing to the API Gateway domain name shown on the API
Gateway record.

If you use Route 53 and configured the hosted zone correctly, this may already
be handled by your setup. If you manage DNS elsewhere, create the required
record with your DNS provider.

Connect from a browser
----------------------

Create a test HTML page.

Update ``wss://ws.example.com`` to match your WebSocket endpoint.

.. code-block:: html

   <!doctype html>
   <html lang="en">
   <head>
       <meta charset="utf-8">
       <title>WebSocket quickstart</title>
   </head>
   <body>
       <h1>WebSocket quickstart</h1>

       <button id="send-message">Send message</button>

       <pre id="output"></pre>

       <script>
           const output = document.getElementById("output");
           const button = document.getElementById("send-message");

           function log(message) {
               output.textContent += `${message}\n`;
           }

           const socket = new WebSocket("wss://ws.example.com?channel=quickstart");

           socket.onopen = function () {
               log("WebSocket connected");
           };

           socket.onmessage = function (event) {
               log(`Received: ${event.data}`);
           };

           socket.onerror = function (event) {
               console.error(event);
               log("WebSocket error");
           };

           socket.onclose = function (event) {
               log(`WebSocket closed: ${event.code}`);
           };

           button.addEventListener("click", function () {
               socket.send(JSON.stringify({
                   action: "default",
                   message: "Hello from the browser"
               }));

               log("Sent message to Django");
           });
       </script>
   </body>
   </html>

Open the page in a browser and click **Send message**.

The browser should send a WebSocket message through API Gateway. Django should
receive it in the ``default`` method and send a reply back to the same
connection.

Using reconnecting-websocket
----------------------------

For real applications, use a reconnecting client so temporary disconnects do not
require the user to refresh the page.

See :doc:`reconnecting_websocket`.

Using WebSocket tokens
----------------------

The quickstart example disables token protection with:

.. code-block:: python

   USE_WS_TOKEN = False

This keeps the first connection example short, but it is not the recommended
production configuration.

For authenticated production usage, enable WebSocket tokens and connect using a
URL like:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=quickstart

See :doc:`websocket_tokens`.

Send to all clients in a channel
--------------------------------

Once clients are connected to the same channel, Django can send a message to
all active sessions in that channel.

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       channel_name="quickstart",
   ).send_message(
       {
           "type": "announcement",
           "message": "Hello everyone in the quickstart channel.",
       }
   )

Send to all connected clients
-----------------------------

You can also broadcast to every active WebSocket session.

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       connected=True,
   ).send_message(
       {
           "type": "system",
           "message": "This message goes to all connected clients.",
       }
   )

Clean up old records
--------------------

Schedule cleanup commands in production to remove stale sessions, expired
tokens, and old rate limit records.

See :doc:`cleanup`.

Troubleshooting
---------------

If the quickstart does not work, check the following:

* the Django site is reachable over HTTPS;
* the API Gateway target base endpoint ends with a trailing slash;
* the Django URL route includes ``<slug:route>``;
* the slug is named ``route``;
* the API Gateway record has been created successfully;
* the custom domain DNS record points to the API Gateway domain;
* AWS credentials are configured correctly;
* IAM permissions allow API Gateway creation and connection management;
* your browser is connecting to ``wss://`` rather than ``https://``;
* the message body includes ``"action": "default"``;
* token validation is disabled for this quickstart, or a valid token is being
  supplied.

For more help, see :doc:`troubleshooting`.

Next steps
----------

After completing the quickstart, continue with:

* :doc:`concepts`;
* :doc:`configuration`;
* :doc:`api_gateway_setup`;
* :doc:`websocket_tokens`;
* :doc:`reconnecting_websocket`;
* :doc:`example`.
