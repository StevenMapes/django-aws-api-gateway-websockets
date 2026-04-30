Permissions
===========

Django-AWS-API-Gateway-WebSockets supports Django permission checks on
WebSocket views.

Permissions allow you to restrict which authenticated users can access
WebSocket handlers.

This is useful for features such as:

* chat rooms;
* dashboards;
* admin notifications;
* moderation tools;
* tenant-specific updates;
* background task progress;
* collaborative editing;
* support consoles.

Overview
--------

WebSocket requests are handled by Django class-based views.

The package allows a ``WebSocketView`` subclass to define permission
requirements. During request dispatch, the user's permissions are checked before
the selected handler is called.

There are two permission options:

``permissions_required``
   The user must have **any** of the listed permissions.

``all_permissions_required``
   The user must have **all** of the listed permissions.

If the user does not satisfy the permission requirements, the request is denied.

Authentication first
--------------------

Permissions only make sense when Django can identify the user.

For authenticated WebSocket usage, you should normally enable WebSocket tokens.
The token flow links the WebSocket connection to the authenticated Django user
and session.

See :doc:`websocket_tokens`.

If a WebSocket connection is anonymous, permission checks will not be useful
unless your application attaches a user through another trusted mechanism.

Require any permission
----------------------

Use ``permissions_required`` when a user may have one of several permissions.

For example, the following view allows users who can either use chat or moderate
chat.

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
           "chat.can_moderate_chat",
       ]

       def default(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

In this example, a user only needs one of the listed permissions.

Require all permissions
-----------------------

Use ``all_permissions_required`` when the user must have every listed
permission.

For example, the following view requires both general chat access and moderation
access.

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ModerationWebSocketView(WebSocketView):
       all_permissions_required = [
           "chat.can_use_chat",
           "chat.can_moderate_chat",
       ]

       def default(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

In this example, a user must have both permissions.

Combining permission options
----------------------------

In most cases, use either ``permissions_required`` or
``all_permissions_required`` on a view.

If your logic is more complex, prefer implementing explicit checks inside your
handler method so the behaviour is clear and easy to test.

For example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatRoomWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
       ]

       def join_room(self, request, *args, **kwargs):
           room_id = self.body.get("room_id")

           if not user_can_join_room(request.user, room_id):
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Permission denied.",
                   },
                   status=403,
               )

           return JsonResponse({"ok": True})

Object-level permissions
------------------------

The built-in view-level permission options are useful for broad checks.

For example:

* can the user use the chat system?
* can the user access the support dashboard?
* can the user receive admin notifications?
* can the user use moderation tools?

For object-level checks, add your own logic inside the handler.

Object-level checks are needed for questions such as:

* can this user join this specific room?
* can this user view this specific tenant?
* can this user edit this document?
* can this user receive notifications for this project?
* can this user broadcast to this channel?

Example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ProjectWebSocketView(WebSocketView):
       permissions_required = [
           "projects.can_use_project_websockets",
       ]

       def subscribe(self, request, *args, **kwargs):
           project_id = self.body.get("project_id")

           if not Project.objects.filter(
               pk=project_id,
               members=request.user,
           ).exists():
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Permission denied.",
                   },
                   status=403,
               )

           return JsonResponse({"ok": True})

Handler whitelisting
--------------------

Permissions control whether the user can access the view or selected handler.

Handler whitelisting controls which methods the client is allowed to request.

You should use both.

For example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       ALLOWED_HANDLERS = {
           "default",
           "send_message",
           "fetch_history",
       }

       permissions_required = [
           "chat.can_use_chat",
       ]

       def default(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

       def send_message(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

       def fetch_history(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

       def _internal_helper(self):
           return None

In this example, clients can request ``send_message`` and ``fetch_history`` but
should not be able to call ``_internal_helper``.

See :doc:`security`.

Creating Django permissions
---------------------------

Django permissions can be created on a model using the model's ``Meta`` class.

Example:

.. code-block:: python

   from django.db import models


   class ChatRoom(models.Model):
       name = models.CharField(max_length=100)

       class Meta:
           permissions = [
               ("can_use_chat", "Can use chat"),
               ("can_moderate_chat", "Can moderate chat"),
               ("can_broadcast_chat", "Can broadcast chat messages"),
           ]

After adding model permissions, create and apply migrations.

.. code-block:: console

   python manage.py makemigrations
   python manage.py migrate

You can then assign permissions to users or groups in Django Admin.

Checking permissions manually
-----------------------------

Inside a handler, you can use Django's normal permission methods.

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class BroadcastWebSocketView(WebSocketView):
       def broadcast(self, request, *args, **kwargs):
           if not request.user.has_perm("chat.can_broadcast_chat"):
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Permission denied.",
                   },
                   status=403,
               )

           return JsonResponse({"ok": True})

This is useful when different handlers on the same view require different
permissions.

Per-handler permissions
-----------------------

If different handlers need different permissions, check them inside each handler.

Example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       permissions_required = [
           "chat.can_use_chat",
       ]

       def send_message(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

       def delete_message(self, request, *args, **kwargs):
           if not request.user.has_perm("chat.can_moderate_chat"):
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Permission denied.",
                   },
                   status=403,
               )

           return JsonResponse({"ok": True})

The view-level permission ensures the user can use chat at all. The
``delete_message`` handler then adds a stricter moderation check.

Channels and permissions
------------------------

Channels are useful for grouping connections, but a channel name should not be
treated as proof of access.

For example, if a user connects to:

.. code-block:: text

   wss://ws.example.com?channel=admin

you should not assume that the user is allowed to receive admin messages just
because the requested channel is ``admin``.

Always verify that the user is allowed to join or use a sensitive channel.

Example:

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.views import WebSocketView


   class AdminNotificationsWebSocketView(WebSocketView):
       all_permissions_required = [
           "staff.can_receive_admin_notifications",
       ]

       def default(self, request, *args, **kwargs):
           return JsonResponse({"ok": True})

For more complex channel rules, validate the requested channel during connection
or in the first subscription message.

Recommended patterns
--------------------

Use view-level permissions for broad access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Good examples:

* can use chat;
* can access dashboard WebSockets;
* can receive staff notifications;
* can use collaborative editing.

Use handler-level checks for specific actions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Good examples:

* can delete this message;
* can moderate this room;
* can broadcast a system message;
* can subscribe to this project;
* can update this document.

Use object-level checks for application data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Good examples:

* user is a member of the room;
* user belongs to the tenant;
* user can view the project;
* user owns the notification stream;
* user has access to the document.

Do not rely on client-supplied values
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Do not trust values such as:

* channel name;
* room ID;
* tenant ID;
* project ID;
* username;
* user ID;
* role name.

Always check these against server-side state.

Example: chat room permissions
------------------------------

This example shows a chat view where users must have chat access, and room
membership is checked inside the handler.

.. code-block:: python

   from django.http import JsonResponse

   from django_aws_api_gateway_websockets.models import WebSocketSession
   from django_aws_api_gateway_websockets.views import WebSocketView

   from .models import ChatRoom


   class ChatWebSocketView(WebSocketView):
       ALLOWED_HANDLERS = {
           "send_message",
       }

       permissions_required = [
           "chat.can_use_chat",
       ]

       def send_message(self, request, *args, **kwargs):
           room_name = self.websocket_session.channel_name
           message = self.body.get("message", "").strip()

           if not ChatRoom.objects.filter(
               slug=room_name,
               members=request.user,
           ).exists():
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Permission denied.",
                   },
                   status=403,
               )

           if not message:
               return JsonResponse(
                   {
                       "ok": False,
                       "error": "Message cannot be empty.",
                   },
                   status=400,
               )

           WebSocketSession.objects.filter(
               channel_name=room_name,
           ).send_message(
               {
                   "type": "chat_message",
                   "message": message,
                   "username": request.user.get_username(),
               }
           )

           return JsonResponse({"ok": True})

Common mistakes
---------------

Assuming the channel is trusted
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A client can choose the channel query string value. Do not assume that a user is
allowed to access a channel just because they connected to it.

Only checking permissions on page load
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A user may keep a WebSocket connection open after their permissions change.

For sensitive actions, check permissions when handling the message, not only
when rendering the page.

Exposing too many handlers
~~~~~~~~~~~~~~~~~~~~~~~~~~

Only expose handlers that the client should be allowed to call.

Use private helper methods for internal logic and keep them out of
``ALLOWED_HANDLERS``.

Returning too much error detail
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Avoid returning detailed permission failure reasons to the client.

Prefer generic messages such as:

.. code-block:: json

   {
     "ok": false,
     "error": "Permission denied."
   }

Log more detailed information server-side if needed.

Testing permissions
-------------------

When testing WebSocket permissions, include cases for:

* anonymous users;
* authenticated users without permission;
* authenticated users with one required permission;
* authenticated users with all required permissions;
* users attempting to access another user's channel;
* users attempting to call disallowed handlers;
* users whose permissions change while connected;
* invalid or missing payload fields.

Production checklist
--------------------

Before deploying permission-protected WebSocket features:

* WebSocket tokens are enabled for authenticated connections.
* Users must be authenticated before requesting tokens.
* View-level permissions are configured.
* Handler-level permission checks are added where needed.
* Object-level permission checks are added where needed.
* Channel access is validated server-side.
* Sensitive handler names are not exposed.
* Error messages do not reveal sensitive information.
* Tests cover allowed and denied access.

Related pages
-------------

See also:

* :doc:`security`;
* :doc:`websocket_tokens`;
* :doc:`rate_limiting`;
* :doc:`client_integration`;
* :doc:`examples`;
* :doc:`troubleshooting`.
