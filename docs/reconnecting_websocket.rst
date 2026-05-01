Using reconnecting-websocket
============================

This guide shows how to use the ``reconnecting-websocket`` JavaScript library
with Django-AWS-API-Gateway-WebSockets.

Why use reconnecting-websocket?
-------------------------------

Browser WebSocket connections can close for many reasons, including:

* temporary network loss;
* browser sleep or tab suspension;
* API Gateway timeouts;
* server restarts;
* mobile network changes.

The browser's built-in ``WebSocket`` class does not automatically reconnect.
The ``reconnecting-websocket`` library wraps the normal WebSocket API and
attempts to reconnect when the connection drops.

Install the JavaScript library
------------------------------

You can include the library from a CDN:

.. code-block:: html

   <script
       src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js"
       integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA=="
       crossorigin="anonymous"
       referrerpolicy="no-referrer">
   </script>

Basic usage
-----------

The simplest connection uses your API Gateway WebSocket URL.

.. code-block:: html

   <script
       src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js"
       integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA=="
       crossorigin="anonymous"
       referrerpolicy="no-referrer">
   </script>

   <script>
       const websocketUrl = "wss://ws.example.com";

       const socket = new ReconnectingWebSocket(websocketUrl);

       socket.onopen = function () {
           console.log("WebSocket connected");
       };

       socket.onmessage = function (event) {
           const message = JSON.parse(event.data);
           console.log("WebSocket message received:", message);
       };

       socket.onerror = function (event) {
           console.error("WebSocket error:", event);
       };

       socket.onclose = function (event) {
           console.log("WebSocket closed:", event.code, event.reason);
       };
   </script>

Using channels
--------------

This package supports grouping WebSocket sessions by channel.

To connect to a specific channel, add the ``channel`` query string parameter to
the WebSocket URL.

.. code-block:: html

   <script>
       const channelName = "my-example-channel";
       const websocketUrl = `wss://ws.example.com?channel=${encodeURIComponent(channelName)}`;

       const socket = new ReconnectingWebSocket(websocketUrl);

       socket.onmessage = function (event) {
           const message = JSON.parse(event.data);
           console.log("Message for channel:", channelName, message);
       };
   </script>

The server can then use the channel name to send messages to all active
connections associated with that channel.

Sending messages to Django
--------------------------

Messages sent from the browser should be JSON encoded.

By default, the ``action`` value is used by API Gateway as the route selection
key.

.. code-block:: html

   <script>
       function sendMessage(action, payload) {
           if (socket.readyState === WebSocket.OPEN) {
               socket.send(JSON.stringify({
                   action: action,
                   ...payload
               }));
           } else {
               console.warn("WebSocket is not currently open");
           }
       }

       sendMessage("default", {
           message: "Hello from the browser"
       });
   </script>

If you have created a custom API Gateway route named ``notifications``, you can
send a message to that route like this:

.. code-block:: html

   <script>
       sendMessage("notifications", {
           message: "Show this notification"
       });
   </script>

Complete example without WebSocket tokens
-----------------------------------------

This example is useful for projects that have disabled WebSocket token
validation or are using an older version of the package.

.. code-block:: html

   <script
       src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js"
       integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA=="
       crossorigin="anonymous"
       referrerpolicy="no-referrer">
   </script>

   <script>
       const channelName = "my-example-channel";
       const websocketUrl = `wss://ws.example.com?channel=${encodeURIComponent(channelName)}`;

       const socket = new ReconnectingWebSocket(websocketUrl, null, {
           debug: false,
           reconnectInterval: 3000,
           maxReconnectInterval: 10000,
           reconnectDecay: 1.5,
           timeoutInterval: 5000,
           maxReconnectAttempts: null
       });

       socket.onopen = function () {
           console.log("WebSocket connected");

           socket.send(JSON.stringify({
               action: "default",
               message: "Hello from the browser"
           }));
       };

       socket.onmessage = function (event) {
           const message = JSON.parse(event.data);
           console.log("WebSocket message received:", message);
       };

       socket.onerror = function (event) {
           console.error("WebSocket error:", event);
       };

       socket.onclose = function (event) {
           console.log("WebSocket closed:", event.code, event.reason);
       };

       function sendMessage(action, payload) {
           if (socket.readyState === WebSocket.OPEN) {
               socket.send(JSON.stringify({
                   action: action,
                   ...payload
               }));
           } else {
               console.warn("WebSocket is not currently open");
           }
       }
   </script>

Using WebSocket tokens
----------------------

Recent versions of this package can use short-lived, single-use WebSocket tokens
to protect authenticated WebSocket connections.

When token protection is enabled, the browser should:

#. request a WebSocket token from Django;
#. open the WebSocket connection with that token;
#. request a fresh token whenever a new connection is required.

The token should be passed using the ``ws_token`` query string parameter.

Example connection URL:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=my-example-channel

Token-aware reconnecting example
--------------------------------

The important difference with token-based connections is that a reconnect should
use a fresh token. A previously used token should not be reused.

.. code-block:: html

   <script
       src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js"
       integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA=="
       crossorigin="anonymous"
       referrerpolicy="no-referrer">
   </script>

   <script>
       const websocketBaseUrl = "wss://ws.example.com";
       const tokenEndpoint = "/api/ws-token/";
       const channelName = "my-example-channel";

       let socket = null;

       function getCookie(name) {
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

       async function getWebSocketToken() {
           const csrfToken = getCookie("csrftoken");

           let request = new Request(
               tokenEndpoint,
               {headers: {'X-CSRFToken': csrftoken}, 'Content-Type': 'application/json'}
           )

           const response = await fetch(request, {method: "POST"});

           if (!response.ok) {
               throw new Error(`Unable to get WebSocket token: ${response.status}`);
           }

           const data = await response.json();
           return data.token;
       }

       async function connectWebSocket() {
           let token;

           try {
               token = await getWebSocketToken();
           } catch (error) {
               console.error(error);
               setTimeout(connectWebSocket, 5000);
               return;
           }

           const websocketUrl = (
               `${websocketBaseUrl}?ws_token=${encodeURIComponent(token)}` +
               `&channel=${encodeURIComponent(channelName)}`
           );

           socket = new ReconnectingWebSocket(websocketUrl, null, {
               debug: false,
               reconnectInterval: 3000,
               maxReconnectInterval: 10000,
               reconnectDecay: 1.5,
               timeoutInterval: 5000,
               maxReconnectAttempts: null
           });

           socket.onopen = function () {
               console.log("WebSocket connected");
           };

           socket.onmessage = function (event) {
               const message = JSON.parse(event.data);
               console.log("WebSocket message received:", message);
           };

           socket.onerror = function (event) {
               console.error("WebSocket error:", event);
           };

           socket.onclose = function (event) {
               console.log("WebSocket closed:", event.code, event.reason);

               setTimeout(function () {
                   if (
                       socket.readyState === WebSocket.CLOSED ||
                       socket.readyState === WebSocket.CLOSING
                   ) {
                       connectWebSocket();
                   }
               }, 3000);
           };
       }

       function sendMessage(action, payload) {
           if (socket && socket.readyState === WebSocket.OPEN) {
               socket.send(JSON.stringify({
                   action: action,
                   ...payload
               }));
           } else {
               console.warn("WebSocket is not connected");
           }
       }

       document.addEventListener("DOMContentLoaded", function () {
           connectWebSocket();
       });
   </script>

Sending a toast notification request
------------------------------------

A common pattern is to send a message to Django and then receive a message back
that the frontend displays as a toast.

Example browser message:

.. code-block:: javascript

   sendMessage("default", {
       type: "toast",
       level: "success",
       message: "The browser is connected"
   });

Example frontend message handler:

.. code-block:: javascript

   socket.onmessage = function (event) {
       const message = JSON.parse(event.data);

       if (message.type === "toast") {
           showToast(message.level, message.message);
           return;
       }

       console.log("WebSocket message received:", message);
   };

   function showToast(level, message) {
       console.log(`[${level}] ${message}`);
   }

Notes and recommendations
-------------------------

When using reconnecting WebSockets:

* always handle ``onopen``, ``onmessage``, ``onerror``, and ``onclose``;
* expect connections to close and reconnect;
* use a fresh WebSocket token for every new connection when token protection is
  enabled;
* include a ``channel`` query string value when you want to group connections;
* send JSON payloads from the browser;
* include the correct ``action`` value for route selection;
* validate all incoming messages in Django;
* avoid sending sensitive data unless the connection is authenticated and
  authorised.

Related pages
-------------

See also:

* :doc:`api_gateway_setup`;
* :doc:`adding_new_routes`;
* :doc:`configuration`;
* :doc:`cleanup`.