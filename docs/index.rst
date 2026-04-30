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

Documentation
-------------

.. toctree::
   :maxdepth: 2
   :caption: User guide

   exposition
   installation
   configuration
   aws_iam_setup
   adding_new_routes
   management_commands/index
   cleanup
   contributing
   changelog

API reference
-------------

.. toctree::
   :maxdepth: 2
   :caption: Reference

   mixins
   views
   modules

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`