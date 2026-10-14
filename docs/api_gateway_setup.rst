API Gateway Setup
=================

This guide walks through setting up an AWS API Gateway WebSocket endpoint for
use with Django-AWS-API-Gateway-WebSockets.

The package can create and configure the API Gateway resources for you, either
from Django Admin or by using management commands.

Before you start
----------------

Before creating the API Gateway, make sure you have completed the following:

* installed the package;
* added ``django_aws_api_gateway_websockets`` to ``INSTALLED_APPS``;
* run the database migrations;
* configured AWS credentials;
* configured the required IAM permissions;
* created a Django WebSocket view;
* added a Django URL pattern for the WebSocket callback endpoint.

For IAM permissions, see :doc:`aws_iam_setup`.

How the API Gateway integration works
-------------------------------------

AWS API Gateway manages the WebSocket connection with the browser or client.

When a WebSocket event occurs, API Gateway sends an HTTP request to your Django
application. Your Django view then handles that request like a normal Django
class-based view.

The usual flow is:

#. The client connects to the API Gateway WebSocket endpoint.
#. API Gateway sends a ``$connect`` event to Django.
#. Django records the WebSocket session.
#. The client sends messages through the WebSocket connection.
#. API Gateway routes those messages to Django.
#. Django handles the message and can send messages back through API Gateway.
#. When the client disconnects, API Gateway sends a ``$disconnect`` event.

.. note::

   API Gateway can add a secret header to every request it sends, so that Django
   can tell the request came from your gateway. This is off by default. Set
   ``WEBSOCKETS["gateway_secret"]`` before you create the gateway to turn it on,
   or see :doc:`gateway_secret` for an existing gateway.

Create the Django URL route
---------------------------

Your Django URL pattern must include a slug parameter named ``route``.

API Gateway uses this value to pass through the route key, such as
``$connect``, ``$disconnect``, ``$default``, or a custom route key.

Example:

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

The ``route`` parameter name is important. The WebSocket view expects that name
when dispatching the request.

Create the WebSocket view
-------------------------

Create a view by subclassing ``WebSocketView``.

You usually need to implement a ``default`` method and any custom route methods
required by your application.

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ExampleWebSocketView(WebSocketView):
       def default(self, request, *args, **kwargs) -> JsonResponse:
           action = self.body.get("action")
           return JsonResponse({"received": action})

The built-in view already handles the connection and disconnection lifecycle.
For most applications, you only need to add handlers for the messages your
frontend sends.

The default method will be called if a method does not exising matching the route/action you wish to take.

Route selection
---------------

API Gateway WebSocket APIs use a route selection expression to decide which
route should receive a message.

By default, this project expects the client payload to contain an ``action``
value.

For example:

.. code-block:: javascript

   exampleSocket.send(JSON.stringify({
       "action": "default",
       "message": "Hello from the browser"
   }));

If you create a custom route named ``notifications``, the client can target it
with:

.. code-block:: javascript

   exampleSocket.send(JSON.stringify({
       "action": "notifications",
       "message": "Show a notification"
   }));

The Django view will look for a matching method name. If a matching method is
not found, the default handler can be used as a fallback.

Create the API Gateway record
-----------------------------

The package provides an ``ApiGateway`` model for storing the API Gateway
configuration in your Django database.

You can create this record through Django Admin, or manually if your project
does not use Django Admin.

The key fields are described below.

API Name
~~~~~~~~

A human-friendly name for the API Gateway.

Use a name that makes the purpose and environment clear, for example:

.. code-block:: text

   Example production websocket API

API Description
~~~~~~~~~~~~~~~

An optional description of the API Gateway.

Default channel name
~~~~~~~~~~~~~~~~~~~~

The default channel assigned to WebSocket sessions when a channel is not
provided by the client.

Channels are used to group WebSocket connections so that your application can
send messages to related clients.

For example, your application might use channels for:

* dashboards;
* chat rooms;
* tenants;
* users;
* apps;
* documents;
* notification groups.

Target base endpoint
~~~~~~~~~~~~~~~~~~~~

The full URL to the Django endpoint that API Gateway should call, excluding the
``route`` slug.

For example, if your Django URL route is:

.. code-block:: text

   https://www.example.com/ws/<slug:route>

then the target base endpoint should be:

.. code-block:: text

   https://www.example.com/ws/

The route value is appended automatically.

Certificate ARN
~~~~~~~~~~~~~~~

The ARN of the AWS Certificate Manager certificate to use for the WebSocket
custom domain.

You need to create this certificate in AWS Certificate Manager before using it
here.

Hosted Zone ID
~~~~~~~~~~~~~~

If you use Route 53 and want to create a custom domain, enter the Route 53 hosted
zone ID.

This is used when mapping the WebSocket custom domain to the API Gateway domain.

API key selection expression
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In most cases, leave this as the default value.

Route selection expression
~~~~~~~~~~~~~~~~~~~~~~~~~~

This controls how API Gateway chooses a route from the client message.

The common default is based on the ``action`` field in the message payload.

If you change this value, make sure your Django WebSocket view uses the same
route selection key.

Route key
~~~~~~~~~

The default route key.

In most cases, you do not need to change this.

Stage name
~~~~~~~~~~

The API Gateway stage name.

If left blank, the package defaults this to ``production``.

Stage description
~~~~~~~~~~~~~~~~~

An optional description for the stage.

Tags
~~~~

Tags may be used to identify AWS resources by environment, application, owner,
or cost centre.

API ID
~~~~~~

This field is populated after the API Gateway has been created in AWS.

API endpoint
~~~~~~~~~~~~

This field is populated after the API Gateway has been created in AWS.

API Gateway domain name
~~~~~~~~~~~~~~~~~~~~~~~

This field is populated after the custom domain setup has run.

If you are configuring DNS manually, this is the value your DNS record should
point to.

API mapping ID
~~~~~~~~~~~~~~

This field is populated after the API mapping has been created.

Create the API Gateway using Django Admin
-----------------------------------------

If you use Django Admin, follow these steps:

#. Open Django Admin.
#. Go to the Django AWS API Gateway WebSockets section.
#. Create a new API Gateway record.
#. Fill in the required fields.
#. Save the record.
#. Return to the API Gateway list page.
#. Select the record.
#. Choose the ``Create API Gateway`` admin action.
#. Click ``Go``.

After the action completes, the API Gateway record should be updated with the
AWS API ID and endpoint details, and its provisioning status should be
``Deployed``.

If creation stops part way, the status shows the last step that worked and
``Last error`` shows the cause. Run the action again to continue from that step.
See :doc:`admin`.

Create the API Gateway using a management command
-------------------------------------------------

If your project does not use Django Admin, create the API Gateway database
record manually, then run:

.. code-block:: console

   python manage.py createApiGateway --pk=1

Replace ``1`` with the primary key of your API Gateway record.

This performs the same API Gateway creation action as the Django Admin action.

If an earlier run stopped part way, run the same command again. It continues from
the recorded step. If the gateway is already complete, the command stops with an
error and changes nothing.

Set up a custom domain
----------------------

A custom domain is optional, but recommended for production deployments.

For example, instead of connecting to an AWS-generated WebSocket URL, your
clients can connect to:

.. code-block:: text

   wss://ws.example.com

Before creating the custom domain, make sure:

* you have an AWS Certificate Manager certificate;
* the certificate covers the WebSocket domain;
* the certificate is validated;
* the certificate ARN has been added to the API Gateway record;
* the hosted zone ID has been added if using Route 53.

Create the custom domain using Django Admin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In Django Admin:

#. Open the API Gateway list page.
#. Select the API Gateway record.
#. Choose the ``Create Custom Domain record for the API`` admin action.
#. Click ``Go``.

After the action completes, the ``Custom Domain Created`` flag should be set,
and the API Gateway domain name should be populated.

Create the custom domain using a management command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you are not using Django Admin, run:

.. code-block:: console

   python manage.py createCustomDomain --pk=1

Replace ``1`` with the primary key of your API Gateway record.

Configure DNS
-------------

If the package creates or identifies the API Gateway domain name, use that value
when configuring DNS.

For example, create a DNS record for:

.. code-block:: text

   ws.example.com

pointing to the API Gateway domain name shown on the API Gateway record.

If you use Route 53 and have configured the hosted zone correctly, this may be
handled as part of the custom domain setup. If you manage DNS elsewhere, create
the required record with your DNS provider.

Configure cookies for subdomains
--------------------------------

If your main Django site and WebSocket endpoint use different subdomains, update
your cookie and CSRF settings so that authentication and session cookies can be
used correctly.

For example, if your main site is:

.. code-block:: text

   https://www.example.com

and your WebSocket endpoint is:

.. code-block:: text

   wss://ws.example.com

you may need settings similar to:

.. code-block:: python

   CSRF_COOKIE_SAMESITE = "Lax"
   CSRF_TRUSTED_ORIGINS = [
       "https://www.example.com",
       "https://ws.example.com",
   ]
   CSRF_COOKIE_DOMAIN = ".example.com"

   SESSION_COOKIE_SAMESITE = "Lax"
   SESSION_COOKIE_NAME = "mysessionid"
   SESSION_COOKIE_DOMAIN = ".example.com"

If your WebSocket endpoint is a subdomain of ``www.example.com``, such as
``ws.www.example.com``, adjust the cookie domain accordingly.

After changing the session cookie name or domain, clear old sessions:

.. code-block:: console

   python manage.py clearsessions

Connect from the browser
------------------------

Once the API Gateway and DNS are ready, connect to the WebSocket endpoint from
the client.

Basic example:

.. code-block:: javascript

   const socket = new WebSocket("wss://ws.example.com?channel=my-example-channel");

   socket.onmessage = function (event) {
       const message = JSON.parse(event.data);
       console.log(message);
   };

   socket.onopen = function () {
       socket.send(JSON.stringify({
           "action": "default",
           "message": "Hello from the browser"
       }));
   };

If WebSocket token protection is enabled, fetch a token before opening the
connection and include it in the connection URL.

For example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=my-example-channel

Adding additional routes
------------------------

By default, requests can be routed to a single Django endpoint. For larger
projects, you may want different WebSocket route keys to call different Django
views.

Additional routes allow API Gateway to send specific route keys to different
target URLs.

This is useful when:

* separate Django apps need separate WebSocket handlers;
* different frontend features need different handlers;
* route-specific views are easier to test and maintain;
* you want to keep WebSocket logic separated by domain.

Additional routes are managed using the ``ApiGatewayAdditionalRoute`` model.

They can be managed:

* as inline forms on the main API Gateway admin page;
* from their own Django Admin page;
* manually in the database;
* through your own deployment process.

If the parent API Gateway has already been deployed, additional routes are
deployed automatically when created, changed or deleted. If the parent API
Gateway has not yet been deployed, they are created during the main API Gateway
deployment.

Each route is marked as deployed once it exists in AWS, and the deployment ID of
the API Gateway is saved. Saving the route again, for example to rename it, does
not create it a second time.

.. versionchanged:: 4.1
   Routes created while the API Gateway was first created are now marked as
   deployed. Before, saving one of them afterwards tried to create it again, which
   failed with a conflict and left an unused integration in AWS. The deployment ID
   was also set only in memory, and is now saved.

.. versionchanged:: 4.1
   Changing the ``route_key`` or ``integration_url`` of a deployed route, or
   deleting it, now changes AWS as well. See :ref:`api-gateway-auto-sync`.

.. _api-gateway-auto-sync:

Keeping AWS in line with your changes
-------------------------------------

.. versionadded:: 4.1

Once an ``ApiGateway`` is deployed, saving a change to it or to one of its
``ApiGatewayAdditionalRoute`` records changes the deployed API in AWS, and
deploys the stage again.

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Local change
     - Change in AWS
   * - Add an additional route
     - Creates the integration and the route.
   * - Change ``integration_url`` of an additional route
     - Updates the route's integration.
   * - Change ``route_key`` of an additional route
     - Renames the route.
   * - Delete an additional route
     - Deletes the route and its integration.
   * - Change ``api_name``, ``api_description``,
       ``api_key_selection_expression`` or ``route_selection_expression``
     - Updates the API.
   * - Change ``target_base_endpoint``
     - Points the ``$connect``, ``$disconnect`` and ``$default`` integrations at
       the new URL.
   * - Change ``stage_description``
     - Deploys the stage with the new description.

Changes to other fields, such as the domain name, certificate or tags, are not
sent to AWS. Changing ``stage_name`` does not rename the stage.

Each additional route stores its AWS route ID and integration ID, so a route is
still found after you rename its key. A route saved before version 4.1 has no
stored IDs, and is found by its route key instead.

If AWS rejects a change, the local change is kept, the error code is saved in
``last_error`` and ``ApiGatewaySyncError`` is raised. In Django Admin the error
shows as a message instead. Fix the cause, then run the ``Sync to AWS`` admin
action. A deletion that fails in AWS is not made locally.

Turning the syncing off
~~~~~~~~~~~~~~~~~~~~~~~

Syncing on save and delete is on by default. To go back to the behaviour before
version 4.1, where editing or deleting a record changes only the local record,
set ``push_changes_to_aws`` to ``False`` in the ``WEBSOCKETS`` setting:

.. code-block:: python

   WEBSOCKETS = {
       "push_changes_to_aws": False,
   }

With it off:

* editing a deployed ``ApiGateway`` changes only the local record;
* editing a deployed ``ApiGatewayAdditionalRoute`` changes only the local record;
* deleting an ``ApiGatewayAdditionalRoute``, one at a time or with a queryset,
  deletes only the local record;
* saving a **new** additional route still creates it in AWS, as it always has, and
  a failure raises the original AWS error (``botocore.exceptions.ClientError``)
  and not ``ApiGatewaySyncError``.

The ``Sync to AWS`` and ``Sync from AWS`` actions and the ``sync_to_aws()`` and
``sync_from_aws()`` methods work whatever the setting says. Use them to change AWS
when you choose to. See :doc:`settings`.

For a single call, pass ``push_to_aws``. ``False`` saves or deletes without calling
AWS at all, and ``True`` changes AWS whatever the setting says:

.. code-block:: python

   gateway.save(push_to_aws=False)
   route.delete(push_to_aws=False)
   route.save(push_to_aws=True)

You can also run the whole comparison yourself. ``sync_to_aws()`` and
``sync_from_aws()`` return a list of sentences describing each change:

.. code-block:: python

   changes = gateway.sync_to_aws()
   changes = gateway.sync_from_aws()

.. warning::

   Deleting an ``ApiGateway`` record does not delete the API in AWS, and does
   not delete its routes there. Deleting an additional route from a queryset
   with ``.delete()`` does delete its route in AWS.

   The credentials used by Django need the ``apigateway:DELETE`` permission to
   delete a route. See :doc:`aws_iam_setup`.

Testing the setup
-----------------

After setup, test the full flow:

#. Confirm the API Gateway record has an API ID and endpoint.
#. Confirm the custom domain is created, if using one.
#. Confirm DNS resolves to the API Gateway domain.
#. Open a WebSocket connection from a browser or test client.
#. Confirm Django receives the ``$connect`` event.
#. Send a message with an ``action`` value.
#. Confirm the correct Django handler is called.
#. Send a message back to the client.
#. Disconnect the client.
#. Confirm Django receives the ``$disconnect`` event.

Troubleshooting
---------------

Creating the API Gateway stops part way
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Open the API Gateway record. The ``Provisioning status`` shows the last step that
worked, and ``Last error`` shows what stopped the next one. Fix the cause, which
is often a missing IAM permission or an AWS limit, then run the
``Create API Gateway`` action or the ``createApiGateway`` command again. See
:doc:`admin`.

Connection fails
~~~~~~~~~~~~~~~~

Check that:

* the WebSocket URL starts with ``wss://`` in production;
* DNS points to the correct API Gateway domain;
* the custom domain certificate is valid;
* the API Gateway stage has been deployed;
* the Django endpoint is publicly reachable by API Gateway;
* the Django URL includes ``<slug:route>``;
* the route slug is named ``route``.

Django returns a bad request
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that API Gateway is forwarding the expected headers and request context.

If you are testing through a proxy or tunnel, some headers may be missing or
changed.

For local development, tunnels such as ngrok can be useful, but you may need to
adjust the required header settings on your WebSocket view.

Messages are always handled by default
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that:

* the client payload contains the correct route selection key;
* the route selection expression in API Gateway matches the Django view setting;
* the custom route exists in API Gateway;
* the view has a method matching the route name;
* the route name does not include the leading ``$`` when implemented as a Python
  method.

Cannot send messages back to clients
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that:

* AWS credentials are configured;
* the IAM policy allows managing WebSocket connections;
* the WebSocket session is still connected;
* the API Gateway endpoint and connection ID are correct;
* stale sessions are cleaned up regularly.

Next steps
----------

After the API Gateway is working, you may want to continue with:

* :doc:`adding_new_routes`;
* :doc:`configuration`;
* :doc:`aws_iam_setup`;
* :doc:`cleanup`;
* :doc:`management_commands/index`.
