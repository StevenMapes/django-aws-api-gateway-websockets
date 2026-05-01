Full chat room example
======================

This example shows how to build a simple chat room using
Django-AWS-API-Gateway-WebSockets.

The example includes:

* an HTML client using ``reconnecting-websocket``;
* fetching historic messages after the WebSocket connects;
* sending a chat message from the browser;
* broadcasting messages to all users in the same room;
* changing rooms by changing the WebSocket channel;
* broadcasting a maintenance message to all connected users from the Django
  shell.

Overview
--------

In this example, each chat room is represented by a WebSocket ``channel``.

For example:

.. code-block:: text

   general
   support
   random

When a browser connects to:

.. code-block:: text

   wss://ws.example.com?channel=general

the connection is associated with the ``general`` channel.

When a user changes room, the browser closes the current WebSocket connection
and opens a new one with a different ``channel`` query string value.

Example assumptions
-------------------

This example assumes:

* the package is installed and configured;
* an API Gateway WebSocket endpoint has been created;
* your WebSocket endpoint is available at ``wss://ws.example.com``;
* WebSocket token protection is disabled for simplicity;
* your Django app is called ``chat``;
* the WebSocket route selection key is ``action``;
* messages sent with ``"action": "chat_message"`` are handled by the
  ``chat_message`` method on the view;
* messages sent with ``"action": "fetch_history"`` are handled by the
  ``fetch_history`` method on the view.

For production deployments, you should also enable authentication,
authorisation, input validation, rate limiting, and WebSocket token protection.

Django model
------------

Create a simple model to store historic chat messages.

.. code-block:: python

   # chat/models.py

   from django.conf import settings
   from django.db import models


   class ChatMessage(models.Model):
       room = models.CharField(max_length=100, db_index=True)
       user = models.ForeignKey(
           settings.AUTH_USER_MODEL,
           on_delete=models.SET_NULL,
           null=True,
           blank=True,
       )
       username = models.CharField(max_length=150)
       message = models.TextField()
       created_at = models.DateTimeField(auto_now_add=True)

       class Meta:
           ordering = ["created_at"]

       def __str__(self):
           return f"[{self.room}] {self.username}: {self.message[:50]}"

Create and apply migrations:

.. code-block:: console

   python manage.py makemigrations chat
   python manage.py migrate

Django WebSocket view
---------------------

Create a WebSocket view that can:

* send historic messages to the current connection;
* receive a chat message;
* store the message;
* broadcast the message to all active connections in the same channel.

.. code-block:: python

   # chat/views.py

   from django.http import JsonResponse
   from django.utils import timezone

   from django_aws_api_gateway_websockets.models import WebSocketSession
   from django_aws_api_gateway_websockets.views import WebSocketView

   from .models import ChatMessage


   class ChatWebSocketView(WebSocketView):
       def fetch_history(self, request, *args, **kwargs):
           room = self.websocket_session.channel_name

           messages = ChatMessage.objects.filter(room=room).order_by("-created_at")[:50]
           messages = reversed(messages)

           self.websocket_session.send_message(
               {
                   "type": "history",
                   "room": room,
                   "messages": [
                       {
                           "username": message.username,
                           "message": message.message,
                           "created_at": message.created_at.isoformat(),
                       }
                       for message in messages
                   ],
               }
           )

           return JsonResponse({"ok": True})

       def chat_message(self, request, *args, **kwargs):
           room = self.websocket_session.channel_name
           message_text = str(self.body.get("message", "")).strip()

           if not message_text:
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Message cannot be empty.",
                   },
                   status=400,
               )

           user = request.user if request.user.is_authenticated else None
           username = user.get_username() if user else "Anonymous"

           message = ChatMessage.objects.create(
               room=room,
               user=user,
               username=username,
               message=message_text,
           )

           WebSocketSession.objects.filter(channel_name=room).send_message(
               {
                   "type": "chat_message",
                   "room": room,
                   "username": message.username,
                   "message": message.message,
                   "created_at": message.created_at.isoformat(),
               }
           )

           return JsonResponse({"ok": True})

       def default(self, request, *args, **kwargs):
           return JsonResponse(
               {
                   "ok": False,
                   "error": "Unknown WebSocket action.",
               },
               status=400,
           )

URL route
---------

Add a URL pattern for API Gateway to call.

The slug parameter must be named ``route``.

.. code-block:: python

   # chat/urls.py

   from django.urls import path

   from .views import ChatWebSocketView


   urlpatterns = [
       path(
           "ws/chat/<slug:route>",
           ChatWebSocketView.as_view(),
           name="chat_websocket",
       ),
   ]

Include the app URLs from your project URL configuration if required.

.. code-block:: python

   # project/urls.py

   from django.urls import include
   from django.urls import path


   urlpatterns = [
       path("", include("chat.urls")),
   ]

API Gateway target endpoint
---------------------------

When creating the API Gateway record, set the target base endpoint to the URL
without the ``route`` slug.

For example, if your Django route is:

.. code-block:: text

   https://www.example.com/ws/chat/<slug:route>

then the API Gateway target base endpoint should be:

.. code-block:: text

   https://www.example.com/ws/chat/

The package appends the route value when configuring API Gateway.

HTML client
-----------

The following HTML page connects to a chat room, fetches historic messages when
the connection opens, sends messages, and allows the user to change rooms.

.. code-block:: html

   <!doctype html>
   <html lang="en">
   <head>
       <meta charset="utf-8">
       <title>WebSocket chat room example</title>

       <style>
           body {
               font-family: sans-serif;
               margin: 2rem;
           }

           #messages {
               border: 1px solid #ccc;
               height: 300px;
               overflow-y: auto;
               padding: 1rem;
               margin-bottom: 1rem;
           }

           .message {
               margin-bottom: 0.5rem;
           }

           .system {
               color: #b45309;
               font-weight: bold;
           }

           .meta {
               color: #666;
               font-size: 0.8rem;
           }
       </style>
   </head>
   <body>
       <h1>Chat room</h1>

       <p>
           Current room:
           <strong id="current-room">general</strong>
       </p>

       <label for="room-select">Change room</label>
       <select id="room-select">
           <option value="general">general</option>
           <option value="support">support</option>
           <option value="random">random</option>
       </select>

       <hr>

       <div id="messages"></div>

       <form id="chat-form">
           <input
               id="message-input"
               type="text"
               placeholder="Type your message"
               autocomplete="off"
               required
           >
           <button type="submit">Send</button>
       </form>

       <script
           src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js"
           integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA=="
           crossorigin="anonymous"
           referrerpolicy="no-referrer">
       </script>

       <script>
           const websocketBaseUrl = "wss://ws.example.com";

           const currentRoomElement = document.getElementById("current-room");
           const roomSelect = document.getElementById("room-select");
           const messagesElement = document.getElementById("messages");
           const chatForm = document.getElementById("chat-form");
           const messageInput = document.getElementById("message-input");

           let currentRoom = roomSelect.value;
           let socket = null;

           function appendMessage(username, message, createdAt) {
               const row = document.createElement("div");
               row.className = "message";

               const meta = document.createElement("div");
               meta.className = "meta";
               meta.textContent = `${username} · ${createdAt || ""}`;

               const body = document.createElement("div");
               body.textContent = message;

               row.appendChild(meta);
               row.appendChild(body);

               messagesElement.appendChild(row);
               messagesElement.scrollTop = messagesElement.scrollHeight;
           }

           function appendSystemMessage(message) {
               const row = document.createElement("div");
               row.className = "message system";
               row.textContent = message;

               messagesElement.appendChild(row);
               messagesElement.scrollTop = messagesElement.scrollHeight;
           }

           function clearMessages() {
               messagesElement.innerHTML = "";
           }

           function sendMessage(action, payload) {
               if (!socket || socket.readyState !== WebSocket.OPEN) {
                   appendSystemMessage("WebSocket is not connected.");
                   return;
               }

               socket.send(JSON.stringify({
                   action: action,
                   ...payload
               }));
           }

           function connectToRoom(roomName) {
               if (socket) {
                   socket.close();
                   socket = null;
               }

               currentRoom = roomName;
               currentRoomElement.textContent = roomName;
               clearMessages();
               appendSystemMessage(`Connecting to ${roomName}...`);

               const websocketUrl = (
                   `${websocketBaseUrl}?channel=${encodeURIComponent(roomName)}`
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
                   appendSystemMessage(`Connected to ${roomName}. Fetching history...`);

                   sendMessage("fetch_history", {});
               };

               socket.onmessage = function (event) {
                   const data = JSON.parse(event.data);

                   if (data.type === "history") {
                       clearMessages();

                       for (const message of data.messages) {
                           appendMessage(
                               message.username,
                               message.message,
                               message.created_at
                           );
                       }

                       appendSystemMessage(`Loaded history for ${data.room}.`);
                       return;
                   }

                   if (data.type === "chat_message") {
                       appendMessage(
                           data.username,
                           data.message,
                           data.created_at
                       );
                       return;
                   }

                   if (data.type === "system") {
                       appendSystemMessage(data.message);
                       return;
                   }

                   console.log("Unhandled WebSocket message:", data);
               };

               socket.onerror = function (event) {
                   console.error("WebSocket error:", event);
               };

               socket.onclose = function (event) {
                   appendSystemMessage(
                       `Disconnected from ${roomName}. Reconnecting if possible...`
                   );
                   console.log("WebSocket closed:", event.code, event.reason);
               };
           }

           roomSelect.addEventListener("change", function () {
               connectToRoom(roomSelect.value);
           });

           chatForm.addEventListener("submit", function (event) {
               event.preventDefault();

               const message = messageInput.value.trim();

               if (!message) {
                   return;
               }

               sendMessage("chat_message", {
                   message: message
               });

               messageInput.value = "";
           });

           connectToRoom(currentRoom);
       </script>
   </body>
   </html>

How fetching history works
--------------------------

When the WebSocket connection opens, the browser sends:

.. code-block:: javascript

   sendMessage("fetch_history", {});

This produces a JSON message like:

.. code-block:: json

   {
     "action": "fetch_history"
   }

API Gateway routes the request to Django. The Django view then calls the
``fetch_history`` method, loads the most recent messages for the current channel,
and sends them back to only the current WebSocket session.

How broadcasting to the current room works
------------------------------------------

When a user sends a chat message, the browser sends:

.. code-block:: javascript

   sendMessage("chat_message", {
       message: "Hello everyone"
   });

The Django view stores the message and then sends it to every active
``WebSocketSession`` in the same channel.

.. code-block:: python

   WebSocketSession.objects.filter(channel_name=room).send_message(
       {
           "type": "chat_message",
           "room": room,
           "username": message.username,
           "message": message.message,
           "created_at": message.created_at.isoformat(),
       }
   )

Because the queryset is filtered by ``channel_name``, only users in the same
room receive the message.

How changing rooms works
------------------------

Changing room means changing the WebSocket channel.

The browser closes the current connection and opens a new one with a different
``channel`` query string parameter.

For example:

.. code-block:: text

   wss://ws.example.com?channel=general

becomes:

.. code-block:: text

   wss://ws.example.com?channel=support

The new connection is stored as a WebSocket session for the new channel. When the
connection opens, the browser fetches message history for the new room.

Broadcasting to all channels from the Django shell
--------------------------------------------------

A systems administrator can send a message to every active WebSocket session
from the Django shell.

Open the shell:

.. code-block:: console

   python manage.py shell

Then run:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession


   WebSocketSession.objects.filter(connected=True).send_message(
       {
           "type": "system",
           "message": "Maintenance will be performed in 5 minutes.",
       }
   )

This sends the message to every active connection, regardless of channel.

Broadcasting to one room from the Django shell
----------------------------------------------

To send a message to only one room, filter by ``channel_name``:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession


   WebSocketSession.objects.filter(
       connected=True,
       channel_name="general",
   ).send_message(
       {
           "type": "system",
           "message": "The general room will be restarted shortly.",
       }
   )

Using WebSocket tokens
----------------------

The HTML example above keeps the WebSocket connection simple by omitting
WebSocket token handling.

If WebSocket token protection is enabled, fetch a token before connecting and
include it in the WebSocket URL.

For example:

.. code-block:: text

   wss://ws.example.com?ws_token=<token>&channel=general

When reconnecting or changing rooms, request a fresh token before opening the new
WebSocket connection.

Security notes
--------------

For production use:

* require authenticated users where appropriate;
* validate message length and content;
* check permissions before allowing users to join restricted rooms;
* avoid trusting the room name without validation;
* rate limit message sending;
* use WebSocket token protection for authenticated sessions;
* escape or sanitise rendered message content;
* schedule cleanup for stale WebSocket sessions.

Related pages
-------------

See also:

* :doc:`api_gateway_setup`;
* :doc:`reconnecting_websocket`;
* :doc:`adding_new_routes`;
* :doc:`cleanup`.