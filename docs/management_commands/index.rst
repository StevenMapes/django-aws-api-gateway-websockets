Management Commands
===================

The package includes Django management commands for managing AWS API Gateway
WebSocket resources and cleanup tasks.

Create an API Gateway
---------------------

Use the API Gateway creation command to create the AWS API Gateway resources for
an existing API Gateway model record.

.. code-block:: console

   python manage.py createApiGateway --pk=<api_gateway_pk>

Replace ``<api_gateway_pk>`` with the primary key of the API Gateway record.

If an earlier run stopped part way, run the command again. It continues from the
step recorded in the record's provisioning status and does not create the API a
second time. If the gateway is already complete, the command stops with an error
and changes nothing.

.. versionchanged:: 4.1
   The command resumes a half-built gateway, and reports a complete gateway with
   a command error. Before, it raised ``DoesNotExist`` for any gateway that had
   been created, including one that had stopped part way.

Create a custom domain
----------------------

Use the custom domain command after the required certificate and DNS
configuration are ready.

.. code-block:: console

   python manage.py createCustomDomain --pk=<api_gateway_pk>

Replace ``<api_gateway_pk>`` with the primary key of the API Gateway record.

The domain and its mapping to the API are separate steps. If the mapping fails,
run the command again and it creates only the mapping.

Update deployed integrations for the gateway secret
---------------------------------------------------

Use the integration update command to add, change or remove the gateway secret
header on the integrations of API Gateways that are already deployed.

.. code-block:: console

   python manage.py updateApiGatewayIntegrations --dry-run
   python manage.py updateApiGatewayIntegrations

The command reads ``WEBSOCKETS["gateway_secret"]``. With a secret set, it adds the
header to each integration that maps ``connectionId``, then deploys the stage.
With no secret set, it removes the header. It leaves other integrations alone.

Use ``--pk=<api_gateway_pk>`` to update one API Gateway record, and ``--dry-run``
to list what would change without changing it.

Run this command before you deploy the secret to your web processes. See
:doc:`/gateway_secret`.

.. versionadded:: 4.1

Clear stale WebSocket sessions
------------------------------

Use the stale-session cleanup command to delete old disconnected WebSocket
session records.

.. code-block:: console

   python manage.py clearWebSocketSessions

This command deletes WebSocket session records where ``connected=False``.

Clean stale WebSocket tokens and rate limit records
---------------------------------------------------

Use the token cleanup command to delete expired WebSocket tokens and old rate
limit records.

.. code-block:: console

   python manage.py cleanupWebSocketTokens

You can also provide cleanup ages if supported by your installed version.

.. code-block:: console

   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

If you do not give ``--token-age``, tokens older than 5 minutes are deleted, or
older than ``WEBSOCKETS["token_expiry_seconds"]`` if that is longer, so a token
that can still be used is never deleted. Give ``--token-age`` to set it yourself.

This command is useful when scheduled from cron, a container scheduler, a
platform task runner, or another periodic job system.

When to use management commands
-------------------------------

Management commands are useful when:

* Django Admin is not enabled;
* API Gateway setup is part of deployment automation;
* cleanup tasks need to run on a schedule;
* infrastructure changes need to be repeatable.
