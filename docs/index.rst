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
   examples
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

Project
-------

.. toctree::
   :maxdepth: 2
   :caption: Project

   architecture
   contributing
   changelog
   release_process
   faq
   license

API reference
-------------

.. toctree::
   :maxdepth: 2
   :caption: API reference

   mixins
   views
   modules

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`