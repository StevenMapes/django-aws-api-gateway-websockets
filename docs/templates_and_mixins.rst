Templates and mixins
====================

Django-AWS-API-Gateway-WebSockets includes mixins that help Django class-based
views pass WebSocket connection information into templates.

These mixins are useful when a page rendered by Django needs to know:

* which API Gateway route to connect to;
* which WebSocket domain to use;
* which channel name to use;
* which route key should be used by the frontend.

Overview
--------

A typical browser page needs enough information to create a WebSocket
connection.

For example, the frontend may need:

.. code-block:: text

   wss://ws.example.com?channel=dashboard

The mixins help by adding values to the template context so your template can
build that connection URL.

Available mixins
----------------

The package provides two template-focused mixins:

``AddWebSocketRouteToContextMixin``
   Adds a configured API Gateway route and channel name to the template context.

``AppChannelWebSocketMixin``
   Extends ``AddWebSocketRouteToContextMixin`` and automatically uses the Django
   app name as both the WebSocket route key and channel name.

AddWebSocketRouteToContextMixin
-------------------------------

Use ``AddWebSocketRouteToContextMixin`` when you want to explicitly define the
route key and channel name used by a view.

It adds these context values:

``api_gateway_route``
   The matching additional route record, including its related API Gateway.

``channel_name``
   The channel name configured on the view.

Basic example
~~~~~~~~~~~~~

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AddWebSocketRouteToContextMixin


   class DashboardView(AddWebSocketRouteToContextMixin, TemplateView):
       template_name = "dashboard/index.html"

       websocket_route_key = "dashboard"
       channel_name = "dashboard"

In this example, the template receives:

* ``api_gateway_route``;
* ``channel_name``.

Template example
~~~~~~~~~~~~~~~~

.. code-block:: html+django

   {% if api_gateway_route %}
       {% with api_gateway_route.api_gateway as websocket %}
           <script>
               const websocketUrl = "wss://{{ websocket.domain_name }}?channel={{ channel_name|urlencode }}";
           </script>
       {% endwith %}
   {% endif %}

You can then use ``websocketUrl`` in your frontend JavaScript.

Example with reconnecting-websocket
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: html+django

   {% if api_gateway_route %}
       {% with api_gateway_route.api_gateway as websocket %}
           <script
               src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js"
               integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA=="
               crossorigin="anonymous"
               referrerpolicy="no-referrer">
           </script>

           <script>
               const websocketUrl = (
                   "wss://{{ websocket.domain_name }}" +
                   "?channel={{ channel_name|urlencode }}"
               );

               const socket = new ReconnectingWebSocket(websocketUrl, null, {
                   debug: false,
                   reconnectInterval: 3000,
                   maxReconnectInterval: 10000,
                   reconnectDecay: 1.5,
                   timeoutInterval: 5000,
                   maxReconnectAttempts: null
               });

               socket.onmessage = function (event) {
                   const data = JSON.parse(event.data);
                   console.log("WebSocket message:", data);
               };
           </script>
       {% endwith %}
   {% endif %}

When to use this mixin
~~~~~~~~~~~~~~~~~~~~~~

Use ``AddWebSocketRouteToContextMixin`` when:

* you want explicit route and channel names;
* one view should connect to a specific WebSocket route;
* the channel is not based on the Django app name;
* you want predictable names across different views.

AppChannelWebSocketMixin
------------------------

Use ``AppChannelWebSocketMixin`` when your convention is:

* the route key is the Django app name;
* the channel name is the Django app name.

This is useful when each Django app has its own WebSocket route or channel.

Basic example
~~~~~~~~~~~~~

Suppose you have a Django app called ``blog``.

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AppChannelWebSocketMixin


   class BlogIndexView(AppChannelWebSocketMixin, TemplateView):
       template_name = "blog/index.html"

In this pattern, the mixin uses the app name as the route key and channel name.

Overriding the channel name
~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can override the automatically selected channel name with
``app_channel_override``.

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AppChannelWebSocketMixin


   class BlogIndexView(AppChannelWebSocketMixin, TemplateView):
       template_name = "blog/index.html"
       app_channel_override = "public_blog"

This keeps the route key based on the app name, while using a custom channel
name.

When to use this mixin
~~~~~~~~~~~~~~~~~~~~~~

Use ``AppChannelWebSocketMixin`` when:

* your route keys match Django app names;
* your channels match Django app names;
* you want convention over configuration;
* you have multiple apps using similar WebSocket patterns.

Template context
----------------

The mixins add values that can be used by templates.

``api_gateway_route``
~~~~~~~~~~~~~~~~~~~~~

This is the additional route record matching the selected route key.

It can be used to access the related API Gateway.

Example:

.. code-block:: html+django

   {% with api_gateway_route.api_gateway as websocket %}
       {{ websocket.domain_name }}
   {% endwith %}

``channel_name``
~~~~~~~~~~~~~~~~

This is the channel name to use when connecting.

Example:

.. code-block:: html+django

   {{ channel_name }}

A browser can include this in the WebSocket URL.

.. code-block:: html+django

   wss://{{ websocket.domain_name }}?channel={{ channel_name|urlencode }}

Using WebSocket tokens in templates
-----------------------------------

For authenticated production usage, WebSocket tokens are recommended.

In that case, the template can expose:

* WebSocket base URL;
* channel name;
* token endpoint URL.

The browser should then request a token before connecting.

Template example
~~~~~~~~~~~~~~~~

.. code-block:: html+django

   {% if api_gateway_route %}
       {% with api_gateway_route.api_gateway as websocket %}
           <script>
               window.websocketConfig = {
                   baseUrl: "wss://{{ websocket.domain_name }}",
                   channel: "{{ channel_name|escapejs }}",
                   tokenEndpoint: "{% url 'websocket_token' %}"
               };
           </script>
       {% endwith %}
   {% endif %}

JavaScript example
~~~~~~~~~~~~~~~~~~

.. code-block:: javascript

   async function getWebSocketToken() {
       const response = await fetch(window.websocketConfig.tokenEndpoint, {
           method: "POST",
           headers: {
               "X-CSRFToken": getCookie("csrftoken"),
               "Content-Type": "application/json"
           },
           credentials: "same-origin"
       });

       if (!response.ok) {
           throw new Error(`Token request failed: ${response.status}`);
       }

       const data = await response.json();
       return data.token;
   }

   async function connectWebSocket() {
       const token = await getWebSocketToken();

       const websocketUrl = (
           `${window.websocketConfig.baseUrl}?ws_token=${encodeURIComponent(token)}` +
           `&channel=${encodeURIComponent(window.websocketConfig.channel)}`
       );

       const socket = new WebSocket(websocketUrl);
       return socket;
   }

See :doc:`websocket_tokens`.

Route setup
-----------

The mixins look up an additional route by route key.

Make sure you have configured the matching route.

For example, if your view uses:

.. code-block:: python

   websocket_route_key = "dashboard"

then you should have an additional route with route key:

.. code-block:: text

   dashboard

See :doc:`adding_new_routes`.

Channel naming strategies
-------------------------

Choose channel names that are:

* predictable;
* safe;
* not overly long;
* not sensitive;
* easy to filter in the database.

Good examples:

.. code-block:: text

   dashboard
   support
   room_123
   tenant_456
   notifications_user_789

Avoid using sensitive values directly, such as:

* email addresses;
* full names;
* secret IDs;
* private business names;
* unvalidated user input.

Security considerations
-----------------------

Do not trust channel names
~~~~~~~~~~~~~~~~~~~~~~~~~~

A channel groups connections. It is not authorization.

Even if a template sets a channel name, the browser can still modify the
connection URL.

Always check server-side permissions for sensitive channels.

Escape template values
~~~~~~~~~~~~~~~~~~~~~~

When writing values into JavaScript, use Django template escaping.

Example:

.. code-block:: html+django

   "{{ channel_name|escapejs }}"

Use ``urlencode`` when placing values into URLs.

Example:

.. code-block:: html+django

   "?channel={{ channel_name|urlencode }}"

Use WebSocket tokens
~~~~~~~~~~~~~~~~~~~~

For authenticated WebSocket features, request a token before connecting.

Do not build authenticated WebSocket connections that rely only on cookies and
channel names.

See :doc:`security` and :doc:`websocket_tokens`.

Example: dashboard page
-----------------------

View
~~~~

.. code-block:: python

   from django.views.generic import TemplateView

   from django_aws_api_gateway_websockets.mixins import AddWebSocketRouteToContextMixin


   class DashboardView(AddWebSocketRouteToContextMixin, TemplateView):
       template_name = "dashboard/index.html"
       websocket_route_key = "dashboard"
       channel_name = "dashboard"

Template
~~~~~~~~

.. code-block:: html+django

   {% if api_gateway_route %}
       {% with api_gateway_route.api_gateway as websocket %}
           <div id="dashboard-status">Connecting...</div>

           <script>
               window.dashboardWebSocket = {
                   baseUrl: "wss://{{ websocket.domain_name }}",
                   channel: "{{ channel_name|escapejs }}",
                   tokenEndpoint: "{% url 'websocket_token' %}"
               };
           </script>

           <script>
               async function getCookie(name) {
                   let cookieValue = null;

                   if (document.cookie && document.cookie !== "") {
                       const cookies = document.cookie.split(";");

                       for (let i = 0; i < cookies.length; i++) {
                           const cookie = cookies[i].trim();

                           if (cookie.substring(0, name.length + 1) === `${name}=`) {
                               cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                               break;
                           }
                       }
                   }

                   return cookieValue;
               }

               async function getToken() {
                   const csrfToken = await getCookie("csrftoken");

                   const response = await fetch(window.dashboardWebSocket.tokenEndpoint, {
                       method: "POST",
                       headers: {
                           "X-CSRFToken": csrfToken,
                           "Content-Type": "application/json"
                       },
                       credentials: "same-origin"
                   });

                   if (!response.ok) {
                       throw new Error(`Token request failed: ${response.status}`);
                   }

                   const data = await response.json();
                   return data.token;
               }

               async function connectDashboardWebSocket() {
                   const token = await getToken();

                   const websocketUrl = (
                       `${window.dashboardWebSocket.baseUrl}?ws_token=${encodeURIComponent(token)}` +
                       `&channel=${encodeURIComponent(window.dashboardWebSocket.channel)}`
                   );

                   const socket = new WebSocket(websocketUrl);

                   socket.onopen = function () {
                       document.getElementById("dashboard-status").textContent = "Connected";
                   };

                   socket.onmessage = function (event) {
                       const data = JSON.parse(event.data);
                       console.log("Dashboard update:", data);
                   };

                   socket.onclose = function () {
                       document.getElementById("dashboard-status").textContent = "Disconnected";
                   };
               }

               connectDashboardWebSocket();
           </script>
       {% endwith %}
   {% else %}
       <p>WebSocket route is not configured.</p>
   {% endif %}

Common problems
---------------

``api_gateway_route`` is empty
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that:

* an additional route exists;
* the route key matches ``websocket_route_key``;
* the route is associated with the correct API Gateway;
* the database contains the expected route record.

Wrong channel is used
~~~~~~~~~~~~~~~~~~~~~

Check:

* ``channel_name`` on ``AddWebSocketRouteToContextMixin``;
* ``app_channel_override`` on ``AppChannelWebSocketMixin``;
* generated JavaScript in the rendered page;
* the WebSocket URL in the browser network tools.

Connection URL is malformed
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check that template values are escaped correctly.

Use:

.. code-block:: html+django

   {{ channel_name|urlencode }}

for query string values.

Token request fails
~~~~~~~~~~~~~~~~~~~

Check:

* token endpoint URL;
* CSRF token;
* session cookie;
* authentication state;
* ``CSRF_TRUSTED_ORIGINS``.

See :doc:`websocket_tokens` and :doc:`troubleshooting`.

Related pages
-------------

See also:

* :doc:`mixins`;
* :doc:`client_integration`;
* :doc:`reconnecting_websocket`;
* :doc:`websocket_tokens`;
* :doc:`adding_new_routes`;
* :doc:`permissions`;
* :doc:`security`;
* :doc:`troubleshooting`.
