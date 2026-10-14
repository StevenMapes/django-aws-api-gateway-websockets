##############
Gateway secret
##############

The gateway secret proves to Django that a request came from your API Gateway. API Gateway adds a secret header to every request it sends to your Django view, and the view refuses a request that does not carry it.

.. versionadded:: 4.1

.. important::

   **The gateway secret is off by default.** Until you set it, the view accepts any request that has the headers API Gateway normally sends and names a registered API ID. A client can copy those headers, so they do not prove where a request came from. Turn the secret on for any production deployment.

   Turning it on needs a change to the integrations of API Gateways you have already deployed. Follow :ref:`gateway-secret-enable` in order, or WebSocket traffic is refused.

The problem it solves
=====================

The URL that API Gateway calls is a public Django URL. The view checks the ``X-Amzn-Apigateway-Api-Id`` header against the API Gateway records in your database, and the other headers API Gateway adds. Every one of those values is chosen by whoever sends the request. The API ID is also visible in the ``wss://`` hostname unless you use a custom domain.

Without a secret, a client that knows a registered API ID can post a forged ``$connect``, message or ``$disconnect`` event directly to your view:

* with another user's connection ID, a forged message runs your handlers as that user. Connection IDs are random and the library never shows them to clients, but they can appear in logs and in the admin;
* a forged ``$connect`` with an invented connection ID stores a session in any channel;
* forged requests can carry any ``X-Forwarded-For`` value, so they avoid the connection rate limit, which keys on the client address.

The secret closes all three. Only API Gateway holds it, because API Gateway adds it to the request after the client has finished with it.

How it works
============

#. You set ``WEBSOCKETS["gateway_secret"]`` in Django settings.
#. API Gateway integrations are created with a request parameter that adds ``X-Ws-Gateway-Secret: <secret>`` to every request sent to Django. New gateways and additional routes get it automatically. Gateways you have already deployed need the :ref:`update command <gateway-secret-enable>`.
#. ``WebSocketView.dispatch`` compares the header with the configured secret before it does anything else, in constant time. A request without a matching header gets a 403 response, and the view runs no database queries and calls no handler.

The check applies to every route: ``$connect``, ``$disconnect`` and messages.

Choosing a secret
=================

Use a long random value, kept out of your repository.

.. code-block:: console

   python -c "import secrets; print(secrets.token_urlsafe(48))"

The secret must be at least 32 characters from ``A-Z a-z 0-9 . _ ~ + / = -``. The secret is written into an API Gateway mapping expression, so quotes, spaces, newlines and other characters are refused. If you read the secret from a file, strip the newline at the end first. The :ref:`system check <gateway-secret-checks>` and the update command both refuse an invalid secret.

Read it from the environment or a secrets manager:

.. code-block:: python

   import os

   WEBSOCKETS = {
       "gateway_secret": os.environ["WS_GATEWAY_SECRET"],
   }

If you already use the ``WEBSOCKETS`` dictionary for other options, add the key to it. See :doc:`settings`.

.. warning::

   The secret is stored in the API Gateway integration configuration, where anyone with read access to the API in AWS (``apigateway:GET``) can see it. Treat that access as access to the secret. Use an ``https://`` URL as the integration target, so the secret is not sent in clear text.

.. _gateway-secret-enable:

Turning it on
=============

Order matters. API Gateway must send the header before Django starts to require it.

New gateways
------------

Set the secret before you create the gateway. The integrations are created with the header, and you can set the secret on your web processes at the same time.

Gateways you have already deployed
----------------------------------

#. **Generate the secret** and store it in your secrets manager.
#. **Update API Gateway first.** Run the command in a shell that has the new setting, which can be a one-off task or a workstation. Your running web processes must not have the setting yet.

   .. code-block:: console

      python manage.py updateApiGatewayIntegrations --dry-run
      python manage.py updateApiGatewayIntegrations

   The command lists the integrations of every created API Gateway record, adds the header to each one that maps ``connectionId`` (the integrations this package creates), and deploys the stage so the change takes effect. It leaves other integrations alone. Use ``--pk`` to update one record, and ``--dry-run`` to see what would change.

   At this point API Gateway sends the header and Django ignores it.
#. **Deploy the secret to your web processes.** From now on the view refuses requests without the header.
#. **Check** that a WebSocket connects and that a message is handled. A 403 response with a ``Rejected a request without a valid gateway secret header`` warning in the log means the header is missing or different. See :ref:`gateway-secret-troubleshooting`.

.. warning::

   If you deploy the secret to the web processes before you run the update command, every WebSocket request is refused until the command has run.

Additional routes
-----------------

An additional route gets the header when it is deployed, if the secret is set at that time. If you add routes before you set the secret, run the update command afterwards.

Rotating the secret
===================

``gateway_secret`` can be a list. API Gateway is sent the **first** secret, and Django accepts **every** secret in the list. This lets you change the secret without refusing traffic.

#. Add the new secret at the front of the list and deploy the web processes. Django now accepts both, and API Gateway still sends the old one.

   .. code-block:: python

      WEBSOCKETS = {
          "gateway_secret": [
              os.environ["WS_GATEWAY_SECRET_NEW"],
              os.environ["WS_GATEWAY_SECRET_OLD"],
          ],
      }

#. Run ``python manage.py updateApiGatewayIntegrations``. API Gateway now sends the new secret.
#. Remove the old secret from the list and deploy again.

Turning it off
==============

Remove the setting from the web processes and deploy. The view accepts requests with or without the header. API Gateway keeps sending it, which does no harm. To remove it from the integrations too, run ``python manage.py updateApiGatewayIntegrations`` with the setting removed.

.. _gateway-secret-checks:

System checks
=============

The package registers two Django system checks.

``django_aws_api_gateway_websockets.E001``
   An error, shown by every ``check`` run, when a configured secret is not a string of at least 32 valid characters. The message never includes the secret.

``django_aws_api_gateway_websockets.W001``
   A warning, shown only by ``python manage.py check --deploy``, when no secret is set. It is a warning, not an error, so existing deployments keep passing the check.

What it does not do
===================

* It does not identify a user. The user still comes from the session that the connection was made with, as before. See :doc:`websocket_tokens`.
* It does not protect against someone who has the secret, such as a person with read access to the API in AWS, or a log that records request headers. Do not log request headers.
* It does not replace HTTPS, ``ALLOWED_HOSTS`` or the other checks in :doc:`security`. It adds to them.
* It does not apply to requests that never reach the view, such as your other Django URLs.

Testing
=======

Without the setting, tests need no header. To test with the secret on, set it with ``override_settings`` and send the header, which Django exposes as ``HTTP_X_WS_GATEWAY_SECRET`` in a ``RequestFactory`` call:

.. code-block:: python

   from django.test import RequestFactory, TestCase, override_settings

   SECRET = "x" * 40


   class GatewaySecretTests(TestCase):
       @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
       def test_request_without_the_secret_is_refused(self):
           request = RequestFactory().post("/ws/default")

           view = MyWebSocketView()
           view.setup(request, route="default")
           response = view.dispatch(request, route="default")

           self.assertEqual(403, response.status_code)

.. _gateway-secret-troubleshooting:

Troubleshooting
===============

Every request gets a 403 response after you set the secret
   API Gateway is not sending the header yet. Run ``python manage.py updateApiGatewayIntegrations``, and check that it printed ``deployed`` for each gateway. Set ``WEBSOCKETS["gateway_secret"]`` in the shell where you run it, with the same value as the web processes.

Only some routes get a 403 response
   Those integrations were not updated. The command updates only integrations that map ``connectionId``. Check an integration in the AWS console, under *Integration request*, for a ``X-Ws-Gateway-Secret`` header mapping.

The update command says an integration is up to date, but requests are refused
   The stage was not deployed, or the secret on the web processes differs from the one in API Gateway. Run the command again, and compare the values.

The command fails with an AWS error
   The identity running it needs ``apigateway:GET``, ``apigateway:PATCH`` and ``apigateway:POST`` on the API's integrations and deployments, which the policy in :doc:`aws_iam_setup` already grants.
