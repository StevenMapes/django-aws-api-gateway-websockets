Adding new routes
=================

Overview
--------

AWS API Gateway WebSocket APIs use routes to decide how incoming messages should
be handled.

A route can be used to send different message types to different Django views or
to different handler methods within a view.

Common route types
------------------

Typical WebSocket API routes include:

* ``$connect`` for new connections;
* ``$disconnect`` for disconnections;
* ``$default`` for messages that do not match another route;
* custom application routes.

Designing routes
----------------

When adding new routes, consider how you want to separate application behaviour.

Common patterns include:

* one default route for all messages;
* one route per Django app;
* one route per frontend feature;
* one route per message type;
* one route per command or action.

Create the Django view
----------------------

Create a Django class-based view that handles the WebSocket request.

The view should validate the incoming payload and perform the required
application action.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       route_key = "notifications"

       def default(self, request, *args, **kwargs):
           # Handle the incoming WebSocket message here.
           return None

Add the URL pattern
-------------------

Add a Django URL pattern for the WebSocket callback endpoint.

.. code-block:: python

   from django.urls import path

   from .views import NotificationsWebSocketView


   urlpatterns = [
       path(
           "websockets/notifications/",
           NotificationsWebSocketView.as_view(),
           name="websocket-notifications",
       ),
   ]

Register the route with API Gateway
-----------------------------------

Create or update the corresponding API Gateway route so that AWS forwards the
route to your Django endpoint.

Depending on your deployment process, this may be done through:

* Django Admin;
* a management command;
* infrastructure as code;
* manual AWS Console configuration.

Testing a route
---------------

After adding a route:

#. deploy or update the API Gateway configuration;
#. connect a WebSocket client;
#. send a message using the route key;
#. confirm that the Django view receives the message;
#. confirm that any reply, multicast, or broadcast message is sent correctly.