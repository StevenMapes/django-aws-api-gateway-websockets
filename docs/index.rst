Django-AWS-API-Gateway-WebSockets Documentation
===============================================
Django-AWS-API-Gateway-WebSockets has been designed to enable you to quickly introduced WebSocket support into your
Django project with minimal configuration. With the right IAM policy setup, this package will create and configure an
AWS ApiGatewway endpoint to forward HTTPS requests to your site allowing to write Class-Based-Views to easily accept
and action requests that are sent across the websocket. The package uses "channel names" to group connections allowing
you to multi-cast messages as well as sending a message to a single connection.

Mixins have been created to help ease development and examples can be found in the example sectcion of this guide


If you're new, check out the :doc:`exposition` to see all the features in
action, or get started with :doc:`installation`. Otherwise, take your pick:

.. toctree::
   :maxdepth: 1

   exposition
   installation
   mixins
   views
   management_commands/index
   examples
   contributing
   changelog

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`