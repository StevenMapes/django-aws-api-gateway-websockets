Message patterns
================

This page describes common messaging patterns used with
Django-AWS-API-Gateway-WebSockets.

The package supports sending messages from Django to connected WebSocket clients
through AWS API Gateway.

Common patterns include:

* replying to the current connection;
* sending to one stored session;
* sending to all sessions for a user;
* sending to all sessions in a channel;
* broadcasting to all connected sessions;
* sending toast notifications;
* sending task progress updates;
* sending lightweight invalidation messages;
* handling stale connections.

Overview
--------

AWS API Gateway owns the WebSocket connection.

Django sends messages back to clients using the API Gateway Management API.

The package provides two main ways to send messages:

``WebSocketSession.send_message()``
   Send to one specific WebSocket connection.

``WebSocketSession.objects.filter(...).send_message()``
   Send to all connected sessions in a queryset.

The queryset version sends to connected sessions in the queryset.

Updating the session from a handler
-----------------------------------

``self.websocket_session`` is loaded at the start of the request. Other requests
can change the same row while your handler runs: ``request_count`` increases with
every message, and ``$disconnect`` sets ``connected=False``.

A plain ``self.websocket_session.save()`` writes every field back from the copy
loaded at the start. That undoes those changes, and can mark a closed connection
as connected again. Write only the fields you changed:

.. code-block:: python

   def set_nickname(self, request, *args, **kwargs):
       self.websocket_session.channel_name = "lobby"
       self.websocket_session.save(update_fields=["channel_name", "updated_on"])

       return JsonResponse({"ok": True})

Include ``updated_on`` so the modification time is still refreshed. For a flag or
a counter, use ``update()`` so the database applies the change:

.. code-block:: python

   from django.db.models import F

   WebSocketSession.objects.filter(pk=self.websocket_session.pk).update(
       request_count=F("request_count") + 1
   )

.. versionchanged:: 4.1
   The library's own ``change_channel`` and ``$disconnect`` handlers, and
   ``WebSocketSession.send_message`` when a connection has gone, now write only
   the fields they change.

Broadcasting to a channel
-------------------------

.. versionchanged:: 4.1
   A queryset broadcast posts to recipients concurrently and no longer stops at
   the first failed recipient.

``WebSocketSession.objects.filter(...).send_message()`` sends the message to
every connected session in the queryset, then returns.

* Each session is posted through its own API Gateway, with one client per
  gateway.
* Up to ``max_workers`` posts (default 10) run at the same time for each gateway.
  Pass ``max_workers=1`` to send one at a time.
* A recipient that fails does not stop the others. The failure is written to the
  ``django_aws_api_gateway_websockets.models`` logger at ``WARNING`` level, with
  the connection ID and the AWS error code. Configure that logger to see it.
* A session whose client has disconnected (AWS answers ``GoneException``) is
  marked ``connected=False``. All such sessions are updated in one query.
* The return value is a list of the AWS responses for the posts that succeeded.
  Failed and disconnected recipients are not in the list, so its length can be
  shorter than the number of sessions.
* A message over the 128 KB AWS limit raises ``ValueError`` before any post is
  made.
* Each client uses a 5 second connect timeout, a 10 second read timeout and the
  botocore ``standard`` retry mode with up to 3 attempts.

.. warning::

   The call blocks until every post has finished. Called from a message handler
   it holds a web worker for that time, and a large channel can reach the API
   Gateway integration timeout (29 seconds) or the worker timeout of your WSGI
   server. Broadcast from a background task for any channel that can grow large.

Broadcasting from a background task
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Queue the broadcast with :func:`django.db.transaction.on_commit` so it runs only
after the data it announces is committed. If the transaction rolls back, nothing
is sent.

.. code-block:: python

   # chat/tasks.py

   from celery import shared_task

   from django_aws_api_gateway_websockets.models import WebSocketSession


   @shared_task
   def broadcast_to_channel(channel_name: str, message: dict) -> None:
       WebSocketSession.objects.filter(
           channel_name=channel_name,
       ).send_message(message)

.. code-block:: python

   # In a WebSocketView handler

   from django.db import transaction

   from .tasks import broadcast_to_channel

   transaction.on_commit(lambda: broadcast_to_channel.delay(room, payload))

Any task queue works. Django 6 includes ``django.tasks`` but ships only backends
that run immediately or discard the task, so use a package such as
``django-tasks`` or Celery to run it in the background.

Message shape
-------------

Messages should be JSON-compatible dictionaries.

A useful convention is to include a ``type`` field.

Example:

.. code-block:: python

   {
       "type": "notification",
       "message": "You have a new notification.",
   }

The frontend can then switch behaviour based on ``type``.

Example browser handler:

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

Recommended message fields
--------------------------

Common fields include:

``type``
   The kind of message being sent.

``message``
   Human-readable text.

``level``
   Severity or style, such as ``success``, ``info``, ``warning``, or ``error``.

``id``
   Application object ID.

``created_at``
   Timestamp.

``channel``
   Channel or room name.

``payload``
   Structured data for the client.

Example:

.. code-block:: json

   {
     "type": "chat_message",
     "channel": "general",
     "username": "alice",
     "message": "Hello everyone",
     "created_at": "2026-04-30T12:00:00Z"
   }

Reply to the current connection
-------------------------------

Use this pattern when the server should respond only to the client that sent the
message.

Example use cases:

* acknowledgement;
* validation error;
* request result;
* private notification;
* task status for one user.

Example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ExampleWebSocketView(WebSocketView):
       def default(self, request, *args, **kwargs):
           self.websocket_session.send_message(
               {
                   "type": "reply",
                   "message": "Django received your message.",
               }
           )

           return JsonResponse({"ok": True})

This sends a message only to the current WebSocket connection.

Send to one stored session
--------------------------

You can also send to a specific stored ``WebSocketSession``.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   session = WebSocketSession.objects.get(pk=1)

   session.send_message(
       {
           "type": "notification",
           "message": "This message was sent to one connection.",
       }
   )

This is useful when you have stored or looked up a specific session.

Send to a user's active sessions
--------------------------------

A user may have multiple active WebSocket sessions, such as multiple browser
tabs or devices.

You can send a message to all active sessions for one user.

.. code-block:: python

   from django.contrib.auth import get_user_model

   User = get_user_model()

   user = User.objects.get(username="alice")

   user.websocket_sessions.filter(
       connected=True,
   ).send_message(
       {
           "type": "notification",
           "message": "This message was sent to all of Alice's active sessions.",
       }
   )

Send to a channel
-----------------

Channels are used to group WebSocket sessions.

Example use cases:

* chat rooms;
* dashboards;
* tenant updates;
* project updates;
* document collaboration;
* notification streams.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       channel_name="general",
   ).send_message(
       {
           "type": "chat_message",
           "channel": "general",
           "username": "alice",
           "message": "Hello general room.",
       }
   )

This sends the message to active sessions in the ``general`` channel.

Broadcast to all connected sessions
-----------------------------------

Broadcasting sends a message to all active WebSocket sessions.

Example use cases:

* maintenance warnings;
* system-wide announcements;
* incident notices;
* global feature flags or reload notices.

Example:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       connected=True,
   ).send_message(
       {
           "type": "system",
           "level": "warning",
           "message": "Maintenance will begin in 5 minutes.",
       }
   )

Use broadcast carefully. Large or frequent broadcasts may increase AWS usage and
application load.

Send a toast notification
-------------------------

Toast notifications are a common WebSocket pattern.

Server-side example:

.. code-block:: python

   self.websocket_session.send_message(
       {
           "type": "toast",
           "level": "success",
           "title": "Saved",
           "message": "Your changes have been saved.",
       }
   )

Frontend example:

.. code-block:: javascript

   socket.onmessage = function (event) {
       const data = JSON.parse(event.data);

       if (data.type === "toast") {
           showToast(data.level, data.title, data.message);
           return;
       }
   };

   function showToast(level, title, message) {
       console.log(`[${level}] ${title}: ${message}`);
   }

Toast payloads commonly include:

* ``type``;
* ``level``;
* ``title``;
* ``message``;
* optional timeout;
* optional action URL.

Send task progress
------------------

WebSockets are useful for showing progress from long-running work.

Example server-side message:

.. code-block:: python

   WebSocketSession.objects.filter(
       channel_name="task_123",
   ).send_message(
       {
           "type": "task_progress",
           "task_id": 123,
           "percent": 75,
           "message": "Processing records.",
       }
   )

Frontend handler:

.. code-block:: javascript

   socket.onmessage = function (event) {
       const data = JSON.parse(event.data);

       if (data.type === "task_progress") {
           updateProgressBar(data.task_id, data.percent, data.message);
           return;
       }
   };

For long-running background jobs, a common pattern is:

#. create a channel for the task;
#. connect the browser to that channel;
#. send progress updates to the channel;
#. send a completion message when finished.

Send lightweight invalidation messages
--------------------------------------

For larger data updates, avoid sending the full data over WebSocket.

Instead, send a small invalidation message and let the browser fetch the updated
data over HTTPS.

Example:

.. code-block:: python

   WebSocketSession.objects.filter(
       channel_name="dashboard",
   ).send_message(
       {
           "type": "resource_updated",
           "resource": "order",
           "id": 123,
           "fetch_url": "/api/orders/123/",
       }
   )

Frontend:

.. code-block:: javascript

   socket.onmessage = async function (event) {
       const data = JSON.parse(event.data);

       if (data.type === "resource_updated") {
           const response = await fetch(data.fetch_url);
           const resource = await response.json();
           updatePage(resource);
       }
   };

This keeps WebSocket messages small and avoids duplicating normal HTTP API
behaviour.

Chat room message
-----------------

A typical chat message pattern is:

#. browser sends a message to Django;
#. Django validates and stores the message;
#. Django sends the message to all sessions in the same channel.

Example:

.. code-block:: python

   from django.db import transaction
   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView

   from .tasks import broadcast_to_channel


   class ChatWebSocketView(WebSocketView):
       def chat_message(self, request, *args, **kwargs):
           room = self.websocket_session.channel_name
           text = self.body.get("message", "").strip()

           if not text:
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Message cannot be empty.",
                   },
                   status=400,
               )

           payload = {
               "type": "chat_message",
               "room": room,
               "username": request.user.get_username(),
               "message": text,
           }
           transaction.on_commit(lambda: broadcast_to_channel.delay(room, payload))

           return JsonResponse({"ok": True})

``broadcast_to_channel`` is the task defined in `Broadcasting from a background
task`_. The handler returns at once and the task does the sending.

See :doc:`example` for a fuller chat room example.

Admin broadcast
---------------

A systems administrator can broadcast from the Django shell.

.. code-block:: console

   python manage.py shell

Then:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import WebSocketSession

   WebSocketSession.objects.filter(
       connected=True,
   ).send_message(
       {
           "type": "system",
           "level": "warning",
           "message": "Maintenance will begin in 5 minutes.",
       }
   )

Message size limits
-------------------

AWS API Gateway WebSocket messages have size limits.

Keep messages compact.

Recommended patterns:

* send IDs instead of full objects;
* send URLs for the browser to fetch larger data;
* avoid sending large lists;
* avoid sending binary data directly;
* compress or paginate data through normal HTTP APIs if needed.

Good WebSocket message:

.. code-block:: json

   {
     "type": "report_ready",
     "report_id": 123,
     "fetch_url": "/reports/123/"
   }

Poor WebSocket message:

.. code-block:: json

   {
     "type": "report_ready",
     "rows": [
       "thousands of rows of data"
     ]
   }

Handling stale connections
--------------------------

Clients may disconnect unexpectedly.

When sending a message, AWS may report that a connection is gone.

This can happen when:

* a browser tab closes;
* a laptop sleeps;
* a mobile network changes;
* API Gateway times out the connection;
* a stale session remains in the database.

Treat stale connections as normal operational behaviour.

Schedule cleanup:

.. code-block:: console

   python manage.py clearWebSocketSessions

See :doc:`cleanup`.

Security considerations
-----------------------

Validate incoming messages
~~~~~~~~~~~~~~~~~~~~~~~~~~

Do not trust client payloads.

Validate:

* required fields;
* string lengths;
* object IDs;
* user permissions;
* channel access;
* message type;
* allowed actions or handlers.

Do not trust channel names
~~~~~~~~~~~~~~~~~~~~~~~~~~

A client can request a channel name.

Always check whether the user is allowed to use that channel.

Avoid sensitive data in messages
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Only send data the connected user is allowed to see.

If broadcasting or multicasting, confirm that every recipient should receive the
message.

Use permissions
~~~~~~~~~~~~~~~

Use Django permissions and object-level checks where needed.

See :doc:`permissions`.

Recommended message conventions
-------------------------------

A consistent message format makes frontend code easier to maintain.

Suggested base shape:

.. code-block:: json

   {
     "type": "message_type",
     "payload": {}
   }

Example:

.. code-block:: json

   {
     "type": "toast",
     "payload": {
       "level": "success",
       "title": "Saved",
       "message": "Your changes have been saved."
     }
   }

Or, for smaller projects, a flatter shape is fine:

.. code-block:: json

   {
     "type": "toast",
     "level": "success",
     "title": "Saved",
     "message": "Your changes have been saved."
   }

Choose one convention and use it consistently.

Testing message patterns
------------------------

When testing message patterns:

* mock AWS API Gateway Management API calls;
* test unicast sends;
* test channel sends;
* test broadcasts;
* test permission failures;
* test stale connection handling;
* test message size behaviour;
* test frontend handling of each ``type``.

See :doc:`testing`.

Related pages
-------------

See also:

* :doc:`client_integration`;
* :doc:`reconnecting_websocket`;
* :doc:`models`;
* :doc:`permissions`;
* :doc:`security`;
* :doc:`cleanup`;
* :doc:`testing`;
* :doc:`example`.
