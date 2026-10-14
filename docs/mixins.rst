######
Mixins
######

The mixins add the details of an API Gateway route to the template context of a Django page, so the page can build the WebSocket URL for its JavaScript.

Both are in ``django_aws_api_gateway_websockets.mixins``. For templates and a complete JavaScript example, see :doc:`templates_and_mixins`. For the generated signatures, see :doc:`api/index`.

``AddWebSocketRouteToContextMixin``
===================================

Add it to a class-based view that has ``get_context_data``, such as a ``TemplateView``. Put it before the Django view class in the bases.

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AddWebSocketRouteToContextMixin


   class DashboardView(AddWebSocketRouteToContextMixin, TemplateView):
       template_name = "dashboard/index.html"

       websocket_route_key = "dashboard"
       channel_name = "dashboard"

Attributes
----------

``websocket_route_key``
   The ``route_key`` of the ``ApiGatewayAdditionalRoute`` to look up. The default is ``"default"``, so set it for any route you have added.

``channel_name``
   The channel the page connects to. The default is an empty string.

Context
-------

The mixin adds two names to the template context.

``api_gateway_route``
   The ``ApiGatewayAdditionalRoute`` whose ``route_key`` is ``websocket_route_key``, with its ``api_gateway`` already loaded, or ``None`` if there is no such route. Use ``api_gateway_route.api_gateway.domain_name`` to build the URL.

``channel_name``
   The value of the ``channel_name`` attribute.

.. code-block:: html+django

   {% if api_gateway_route %}
       <script>
           const websocketUrl = "wss://{{ api_gateway_route.api_gateway.domain_name }}?channel={{ channel_name|urlencode }}";
       </script>
   {% endif %}

.. note::

   The lookup uses additional routes only. The ``$connect``, ``$disconnect`` and ``$default`` routes are not stored as ``ApiGatewayAdditionalRoute`` records, so with the default ``websocket_route_key`` of ``"default"`` the context holds ``None`` unless you added an additional route with that key. If more than one API Gateway has an additional route with the same key, the one with the lowest ID is used, so give each route key a name that only one gateway uses.

``AppChannelWebSocketMixin``
============================

A version of the first mixin that names the route and the channel after the Django app that holds the view. It saves you from setting the two attributes in every view of an app.

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AppChannelWebSocketMixin


   class ChatPageView(AppChannelWebSocketMixin, TemplateView):
       template_name = "chat/index.html"

If this view is in the ``chat`` app, then ``websocket_route_key`` and ``channel_name`` are both ``"chat"``, and the route with the key ``chat`` is looked up.

How the name is found
---------------------

The mixin resolves the URL of the request and takes the Python package of the matching view. It needs ``self.request``, which Django sets before ``get_context_data`` runs, and a URL that resolves.

The name is the full Python package of the view, so a view in ``shop/chat/views.py`` gives ``shop.chat``. A channel name can contain only letters, numbers, underscores and hyphens, so a name with a dot is refused when the browser connects. Set ``app_channel_override`` for an app inside another package.

Attributes
----------

``app_channel_override``
   Set it to use a different channel name. The route key is still the name of the app. The default is ``None``.

Context
-------

The same two names as ``AddWebSocketRouteToContextMixin``: ``api_gateway_route`` and ``channel_name``. The same note about additional routes applies.

See also
========

* :doc:`templates_and_mixins`, for templates and JavaScript;
* :doc:`adding_new_routes`, for adding a route to an API Gateway;
* :doc:`views`, for the view API Gateway calls.
