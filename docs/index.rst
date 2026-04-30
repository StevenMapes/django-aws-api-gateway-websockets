Django-AWS-API-Gateway-WebSockets
=================================

Django-AWS-API-Gateway-WebSockets helps Django projects receive and send
messages over AWS API Gateway WebSocket APIs.

It provides Django models, views, mixins, queryset helpers, admin actions, and
management commands for working with WebSocket connections backed by AWS API
Gateway.

The package is designed to make it easier to:

* receive WebSocket messages in Django class-based views;
* send a message back to the current connection;
* send messages to all active sessions in a channel;
* multicast or broadcast messages to groups of connected clients;
* maintain WebSocket session state in your Django database;
* create and manage API Gateway resources from Django.

Documentation map
-----------------

If you are new to the project, start with:

* :doc:`quickstart` for the shortest path to a working setup;
* :doc:`concepts` for the main terms used by the package;
* :doc:`installation` for installation steps;
* :doc:`configuration` and :doc:`settings` for Django and AWS configuration.

If you are setting up AWS, read:

* :doc:`aws_iam_setup` for IAM permissions;
* :doc:`api_gateway_setup` for creating the API Gateway;
* :doc:`adding_new_routes` for custom WebSocket routes;
* :doc:`admin` for managing API Gateway records through Django Admin.

If you are building a frontend client, read:

* :doc:`client_integration` for browser connection patterns;
* :doc:`reconnecting_websocket` for reconnecting client behaviour;
* :doc:`websocket_tokens` for authenticated WebSocket connections;
* :doc:`templates_and_mixins` for adding WebSocket context to Django templates.

If you are sending messages from Django, read:

* :doc:`message_patterns` for unicast, multicast, broadcast, toasts, and task
  progress examples;
* :doc:`models` for the models used to track sessions and send messages;
* :doc:`example` for a complete chat room example.

If you are preparing for production, read:

* :doc:`security` for the security model;
* :doc:`permissions` for Django permission checks;
* :doc:`rate_limiting` for connection and token rate limits;
* :doc:`deployment` for production deployment guidance;
* :doc:`cleanup` for scheduled cleanup tasks;
* :doc:`troubleshooting` for common problems.

If you are contributing or maintaining the project, read:

* :doc:`testing` for testing guidance;
* :doc:`contributing` for contribution instructions;
* :doc:`upgrade_guide` for upgrade considerations;
* :doc:`release_process` for release steps;
* :doc:`architecture` for the project architecture.

Getting started
---------------

.. toctree::
   :maxdepth: 2
   :caption: Getting started

   exposition
   quickstart
   concepts
   installation
   configuration
   settings

AWS setup
---------

.. toctree::
   :maxdepth: 2
   :caption: AWS setup

   aws_iam_setup
   api_gateway_setup
   adding_new_routes

Usage
-----

.. toctree::
   :maxdepth: 2
   :caption: Usage

   client_integration
   reconnecting_websocket
   templates_and_mixins
   message_patterns
   example
   management_commands/index
   cleanup

Security and operations
-----------------------

.. toctree::
   :maxdepth: 2
   :caption: Security and operations

   security
   websocket_tokens
   permissions
   rate_limiting
   deployment
   local_development
   troubleshooting
   testing
   upgrade_guide

Project
-------

.. toctree::
   :maxdepth: 2
   :caption: Project

   architecture
   contributing
   release_process
   faq
   license
   changelog

API reference
-------------

.. toctree::
   :maxdepth: 2
   :caption: API reference

   modules
   models
   views
   mixins
   admin
   api/index

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
