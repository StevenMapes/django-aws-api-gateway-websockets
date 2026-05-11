Client integration
==================

This page explains how browser clients connect to
Django-AWS-API-Gateway-WebSockets through AWS API Gateway.

It covers:

* WebSocket URL format;
* channels;
* WebSocket tokens;
* message payload structure;
* handler selection;
* receiving messages;
* reconnecting clients;
* room or channel changes;
* common client-side patterns.

Overview
--------

The browser does not connect directly to Django.

Instead, the browser connects to AWS API Gateway using a WebSocket URL such as:

.. code-block:: text

   wss://ws.example.com

AWS API Gateway keeps the WebSocket connection open and forwards connection,
message, and disconnection events to Django over HTTP.

Django receives those events in a ``WebSocketView`` subclass.

Basic connection
----------------

A basic browser connection looks like this:

.. code-block:: javascript

   const socket = new WebSocket("wss://ws.example.com");

   socket.onopen = function () {
       console.log("Connected");
   };

   socket.onmessage = function (event) {
       const message = JSON.parse(event.data);
       console.log("Received:", message);
   };

   socket.onerror = function (event) {
       console.error("WebSocket error:", event);
   };

   socket.onclose = function (event) {
       console.log("Closed:", event.code, event.reason);
   };

For production applications, use ``wss://`` rather than ``ws://``.

WebSocket URL format
--------------------

A typical WebSocket URL may include:

* the API Gateway WebSocket domain;
* an optional ``channel`` query string value;
* an optional ``ws_token`` query string value.

Example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

If WebSocket token protection is disabled, the URL may only include a channel:

.. code-block:: text

   wss://ws.example.com?channel=notifications

Channels
--------

Channels group WebSocket sessions.

For example:

.. code-block:: text

   wss://ws.example.com?channel=general
   wss://ws.example.com?channel=support
   wss://ws.example.com?channel=notifications

Django can send messages to all connected sessions in a channel.

Example server-side send:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       channel_name="notifications",
   ).send_message(
       {
           "type": "notification",
           "message": "You have a new notification.",
       }
   )

Do not treat the channel name as proof of access. Validate permissions
server-side before allowing users to access sensitive channels.

See :doc:`permissions`.

WebSocket tokens
----------------

For authenticated WebSocket connections, use WebSocket tokens.

The browser first requests a token from Django over a normal CSRF-protected HTTP
request. The browser then includes that token in the WebSocket URL.

Example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=notifications

Tokens are short-lived and single-use. Request a fresh token for each new
connection attempt.

See :doc:`websocket_tokens`.

Requesting a token
------------------

Example JavaScript helper:

.. code-block:: javascript

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

       const response = await fetch("/api/ws-token/", {
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

Connecting with a token
-----------------------

.. code-block:: javascript

   async function connectWebSocket() {
       const token = await getWebSocketToken();
       const channel = "notifications";

       const websocketUrl = (
           `wss://ws.example.com?ws_token=${encodeURIComponent(token)}` +
           `&channel=${encodeURIComponent(channel)}`
       );

       const socket = new WebSocket(websocketUrl);

       socket.onopen = function () {
           console.log("Connected");
       };

       socket.onmessage = function (event) {
           const message = JSON.parse(event.data);
           console.log("Received:", message);
       };

       return socket;
   }

Message payloads
----------------

Messages sent from the browser should normally be JSON.

Example:

.. code-block:: javascript

   socket.send(JSON.stringify({
       action: "default",
       message: "Hello from the browser"
   }));

The default API Gateway route selection expression commonly uses the ``action``
field.

Handler selection
-----------------

The view can dispatch messages to different methods based on a handler or action
value.

For example, the browser may send:

.. code-block:: javascript

   socket.send(JSON.stringify({
       action: "chat_message",
       message: "Hello everyone"
   }));

A Django view can then implement a matching handler.

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       def chat_message(self, request, *args, **kwargs):
           message = self.body.get("message")
           return JsonResponse({"ok": True})

Depending on your view configuration, you may prefer to use ``handler`` instead
of ``action`` for Django-side handler selection.

Example:

.. code-block:: javascript

   socket.send(JSON.stringify({
       handler: "chat_message",
       message: "Hello everyone"
   }));

Keep the client payload, API Gateway route selection expression, and Django view
configuration aligned.

Receiving messages
------------------

Messages sent by Django are received in the browser's ``onmessage`` handler.

.. code-block:: javascript

   socket.onmessage = function (event) {
       const data = JSON.parse(event.data);

       if (data.type === "notification") {
           showNotification(data.message);
           return;
       }

       if (data.type === "chat_message") {
           appendChatMessage(data.username, data.message);
           return;
       }

       console.log("Unhandled message:", data);
   };

A useful convention is to include a ``type`` field in server-sent messages.

Example:

.. code-block:: json

   {
     "type": "chat_message",
     "username": "alice",
     "message": "Hello"
   }

Sending messages safely
-----------------------

Before sending, check that the socket is open.

.. code-block:: javascript

   function sendMessage(socket, action, payload) {
       if (!socket || socket.readyState !== WebSocket.OPEN) {
           console.warn("WebSocket is not connected");
           return;
       }

       socket.send(JSON.stringify({
           action: action,
           ...payload
       }));
   }

Example:

.. code-block:: javascript

   sendMessage(socket, "chat_message", {
       message: "Hello from the browser"
   });

Changing channels
-----------------

A channel is selected when the WebSocket connection is opened.

To change channels, close the current connection and open a new one with a
different ``channel`` query string value.

.. code-block:: javascript

   let socket = null;
   let currentChannel = "general";

   async function connectToChannel(channel) {
       if (socket) {
           socket.close();
           socket = null;
       }

       currentChannel = channel;

       const token = await getWebSocketToken();

       const websocketUrl = (
           `wss://ws.example.com?ws_token=${encodeURIComponent(token)}` +
           `&channel=${encodeURIComponent(channel)}`
       );

       socket = new WebSocket(websocketUrl);
   }

When token protection is enabled, request a new token for the new connection.

Reconnect handling
------------------

Network interruptions are normal. Browsers may also suspend tabs or lose
connections when devices sleep.

For real applications, use a reconnecting client.

See :doc:`reconnecting_websocket`.

If WebSocket tokens are enabled, each reconnect must use a fresh token.


Client-side validation
----------------------

Client-side validation improves usability, but it is not security.

Always validate messages again in Django.

Client-side checks may include:

* message length;
* required fields;
* disabled send button while disconnected;
* avoiding duplicate sends;
* validating room names before connecting.

Server-side checks are still required.

Example complete client
-----------------------

This example connects to a channel, sends messages, and receives typed messages.

.. code-block:: html

   <!doctype html>
   <html lang="en">
   <head>
       <meta charset="utf-8">
       <title>WebSocket client example</title>
   </head>
   <body>
       <h1>WebSocket client example</h1>

       <form id="message-form">
           <input id="message-input" type="text" autocomplete="off" required>
           <button type="submit">Send</button>
       </form>

       <pre id="output"></pre>

       <script>
           const output = document.getElementById("output");
           const form = document.getElementById("message-form");
           const input = document.getElementById("message-input");

           let socket = null;

           function log(message) {
               output.textContent += `${message}\n`;
           }

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

               const response = await fetch("/api/ws-token/", {
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

           async function connect() {
               const token = await getWebSocketToken();
               const channel = "general";

               const websocketUrl = (
                   `wss://ws.example.com?ws_token=${encodeURIComponent(token)}` +
                   `&channel=${encodeURIComponent(channel)}`
               );

               socket = new WebSocket(websocketUrl);

               socket.onopen = function () {
                   log("Connected");
               };

               socket.onmessage = function (event) {
                   const data = JSON.parse(event.data);
                   log(`Received: ${JSON.stringify(data)}`);
               };

               socket.onerror = function () {
                   log("WebSocket error");
               };

               socket.onclose = function (event) {
                   log(`Closed: ${event.code}`);
               };
           }

           function sendMessage(action, payload) {
               if (!socket || socket.readyState !== WebSocket.OPEN) {
                   log("Cannot send: WebSocket is not connected");
                   return;
               }

               socket.send(JSON.stringify({
                   action: action,
                   ...payload
               }));
           }

           form.addEventListener("submit", function (event) {
               event.preventDefault();

               sendMessage("chat_message", {
                   message: input.value
               });

               input.value = "";
           });

           connect();
       </script>
   </body>
   </html>

Security recommendations
------------------------

For production clients:

* use ``wss://``;
* use WebSocket tokens for authenticated connections;
* request a fresh token for every new connection;
* do not reuse tokens;
* validate client input for usability;
* validate all data again on the server;
* use reconnect backoff;
* avoid exposing sensitive information in channel names;
* handle errors and closed connections gracefully.

Related pages
-------------

See also:

* :doc:`websocket_tokens`;
* :doc:`reconnecting_websocket`;
* :doc:`permissions`;
* :doc:`example`;
* :doc:`security`;
* :doc:`troubleshooting`.
