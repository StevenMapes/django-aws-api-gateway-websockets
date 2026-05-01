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

Create a custom domain
----------------------

Use the custom domain command after the required certificate and DNS
configuration are ready.

.. code-block:: console

   python manage.py createCustomDomain --pk=<api_gateway_pk>

Replace ``<api_gateway_pk>`` with the primary key of the API Gateway record.

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

This command is useful when scheduled from cron, a container scheduler, a
platform task runner, or another periodic job system.

When to use management commands
-------------------------------

Management commands are useful when:

* Django Admin is not enabled;
* API Gateway setup is part of deployment automation;
* cleanup tasks need to run on a schedule;
* infrastructure changes need to be repeatable.
