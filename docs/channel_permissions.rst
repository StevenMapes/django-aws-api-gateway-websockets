###################
Channel permissions
###################

Channel permissions control who may join a WebSocket channel. You store a rule for a channel name in the database, and the library checks it when a connection is made and when a client changes channel.

.. versionadded:: 4.1

.. important::

   **Every channel is open to every user by default.** A channel with no rule can be joined by anyone who can connect, including anonymous users, and the library does not check what they are allowed to see. This keeps existing projects working after an upgrade.

   This default is planned to change in a future major version, so that a channel without a rule is refused. See :ref:`channel-permissions-future`.

Why channels need a rule
========================

A channel is only a name. A client chooses it with the ``channel`` query string parameter when it connects, or with the ``change_channel`` message afterwards. Broadcasts go to every session in the channel:

.. code-block:: python

   WebSocketSession.objects.filter(channel_name="tenant_456").send_message(
       {"type": "invoice_paid"}
   )

If a channel carries data that only some users may see, such as a channel for one tenant or one user, a user who knows or guesses the name can join it and read the broadcasts. A predictable name is not secret and does not protect the channel. A rule for the channel does.

How a join is decided
=====================

When a client connects, or sends ``change_channel``, ``WebSocketView.can_join_channel`` runs with the requested channel name:

#. The name must pass the length and character checks. If it fails, the response is 400 and no rule is consulted.
#. The view looks up the ``ChannelPermission`` row for the name, with ``get_channel_permission``.
#. If there is no row, the join is allowed, unless the view sets ``ALLOW_UNLISTED_CHANNELS = False``.
#. If there is a row, the user must pass its access level.
#. A refused join gets a 403 response. On connect, no session is created and the attempt counts as a failed connection for rate limiting. On ``change_channel``, the session stays in its current channel.

Access levels
=============

Each ``ChannelPermission`` row has one access level.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Access level
     - Who may join
   * - Allow all
     - Everyone, including anonymous users. Use it to record that a channel is public on purpose, which matters if you later set ``ALLOW_UNLISTED_CHANNELS = False``.
   * - Super admin only
     - Active users with ``is_superuser`` set.
   * - Staff only
     - Active users with ``is_staff`` set, and active superusers.
   * - Requires Django permissions
     - Active users who satisfy the permission rules for the channel. Superusers always pass.

Anonymous and inactive users are refused by every level except Allow all. An access level the library does not recognise refuses everyone, so a row never opens a channel by mistake.

Permission rules: AND and OR
============================

A channel set to Requires Django permissions has one or more **rules**. Each rule holds one or more Django permissions.

* Within one rule, the user needs **all** the permissions (AND).
* Between rules, the user needs to satisfy **any one** rule (OR).

This lets you describe any combination of AND and OR.

User must have permission A or permission B
-------------------------------------------

Add two rules. The first holds A and the second holds B.

.. code-block:: text

   Rule 1: A
   Rule 2: B

User must have permission A and permission B
--------------------------------------------

Add one rule that holds both.

.. code-block:: text

   Rule 1: A, B

User must have (A and B) or C
-----------------------------

Add two rules. The first holds A and B, and the second holds C.

.. code-block:: text

   Rule 1: A, B
   Rule 2: C

.. note::

   A channel with no rules, and a rule with no permissions, admit only superusers. An empty rule never means "everyone". Add an Allow all row for a public channel.

The permissions are the project's own Django permissions, such as ``chat.view_message`` or a custom permission from your models' ``Meta.permissions``. The rule checks them with ``user.has_perms()``, so it works with any authentication backend that supports object-independent permissions.

Setting up in Django Admin
==========================

#. Open **Channel permissions** and choose **Add channel permission**.
#. Enter the exact **channel name**, for example ``reports``. It may contain letters, numbers, underscores and hyphens, up to 128 characters.
#. Choose the **access level**.
#. For Requires Django permissions, add a rule under **Channel permission rules**, and move the permissions it needs from *Available* to *Chosen*. Use **Add another Channel permission rule** for each alternative.
#. Save.

The list page shows the rules of each channel in the form ``(A AND B)  OR  (C)``.

.. warning::

   Anyone who can add or change channel permissions controls who can join channels. Give that permission only to people you trust with that decision.

Setting up in code
==================

The same rows can be created from code, for example in a data migration or a management command.

.. code-block:: python

   from django.contrib.auth.models import Permission

   from django_aws_api_gateway_websockets.models import (
       ChannelPermission,
       ChannelPermissionRule,
   )

   channel = ChannelPermission.objects.create(
       channel_name="reports",
       access=ChannelPermission.Access.PERMISSIONS,
   )

   # (reports.view_report AND reports.export_report) OR reports.administer
   rule = ChannelPermissionRule.objects.create(channel_permission=channel)
   rule.permissions.set(
       Permission.objects.filter(
           content_type__app_label="reports",
           codename__in=["view_report", "export_report"],
       )
   )
   other = ChannelPermissionRule.objects.create(channel_permission=channel)
   other.permissions.set(Permission.objects.filter(codename="administer"))

.. _channel-permissions-unlisted:

Unlisted channels
=================

``ALLOW_UNLISTED_CHANNELS`` is a class attribute on ``WebSocketView``. It decides what happens to a channel with no row.

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class ChatWebSocketView(WebSocketView):
       ALLOW_UNLISTED_CHANNELS = False

The default is ``True``. With ``False``, only channels that have a row can be joined, so you decide each channel in advance. This is the behaviour planned as the future default. An empty channel name, which is what a connection gets when it names no channel and the API Gateway has no default, has no row either, so it is refused too.

``python manage.py check --deploy`` warns with ``django_aws_api_gateway_websockets.W004`` for each routed view that still has the default, so a view you forgot is reported before release.

Permissions on the connection itself
====================================

``permissions_required`` and ``all_permissions_required`` apply to the messages a connected client sends. They do not apply to the connection itself by default. Set ``CHECK_PERMISSIONS_ON_CONNECT = True`` to apply them to the connect route too.

.. code-block:: python

   class ChatWebSocketView(WebSocketView):
       CHECK_PERMISSIONS_ON_CONNECT = True
       permissions_required = ["chat.use_chat"]

The default is ``False``, and is also planned to change. See :ref:`channel-permissions-future`.

What a rule does not do
=======================

* **It is checked when a client joins, not afterwards.** If you change a rule, or remove a permission from a user, a session that is already in the channel stays in it and keeps receiving broadcasts until it disconnects or changes channel. To remove a session, filter it out of your broadcasts, or move it with ``WebSocketSession.objects.filter(...).update(channel_name="")``.
* **It does not filter broadcasts.** ``send_message`` sends to every connected session in the queryset. The rule protects who may join, not who your code sends to.
* **It does not authenticate the user.** The rule uses ``request.user``. On a connection with ``USE_WS_TOKEN = False`` that is the user Django's authentication middleware found, which may be anonymous. Keep ``USE_WS_TOKEN = True`` for channels that need an identity. See :doc:`websocket_tokens`.

Extending the checks
====================

The library gives you three places to change how channels are checked.

``WebSocketView.can_join_channel(request, channel_name)``
   The decision. Override it to add rules that do not fit a stored row, such as "a user may join only their own channel". Call ``super().can_join_channel()`` to keep the stored rules, or leave the call out to replace them.

``WebSocketView.get_channel_permission(channel_name)``
   Returns the ``ChannelPermission`` for a name, or ``None``. Override it to cache the lookup, or to build a rule from the name.

``ChannelPermission.allows(user)``
   The check for one row. You can call it from your own code, for example to decide who sees a link to a channel.

A user may join only their own channel, and the stored rules apply to everything else:

.. code-block:: python

   from django_aws_api_gateway_websockets.views import WebSocketView


   class NotificationsWebSocketView(WebSocketView):
       def can_join_channel(self, request, channel_name: str) -> bool:
           if channel_name.startswith("notifications_user_"):
               user = request.user
               return (
                   user.is_authenticated
                   and channel_name == f"notifications_user_{user.pk}"
               )

           return super().can_join_channel(request, channel_name)

Rules derived from the channel name, without a row for every tenant:

.. code-block:: python

   from django_aws_api_gateway_websockets.models import ChannelPermission
   from django_aws_api_gateway_websockets.views import WebSocketView


   class TenantWebSocketView(WebSocketView):
       def get_channel_permission(self, channel_name: str):
           if channel_name.startswith("tenant_"):
               return ChannelPermission(
                   channel_name=channel_name,
                   access=ChannelPermission.Access.STAFF_ONLY,
               )

           return super().get_channel_permission(channel_name)

Cache the lookup to avoid a query on every join:

.. code-block:: python

   from django.core.cache import cache

   from django_aws_api_gateway_websockets.views import WebSocketView


   class CachedWebSocketView(WebSocketView):
       def get_channel_permission(self, channel_name: str):
           key = f"channel-permission:{channel_name}"
           channel_permission = cache.get(key)

           if channel_permission is None:
               channel_permission = super().get_channel_permission(channel_name)
               cache.set(key, channel_permission, 60)

           return channel_permission

This caches only channels that have a row. A channel with no row is looked up on every join. Keep the time short, because a change to a row then takes that long to apply.

Queries
=======

* Joining an unlisted channel takes one query, for the row.
* Allow all, Super admin only and Staff only take one query. Superusers pass without loading any rules.
* Requires Django permissions takes two more queries to load the rules and their permissions, whatever the number of rules. Django's permission backend then loads the user's permissions once, and caches them on the user object for the rest of the request.

Testing
=======

Test the rule with the model, which needs no connection:

.. code-block:: python

   from django.contrib.auth import get_user_model
   from django.test import TestCase

   from django_aws_api_gateway_websockets.models import ChannelPermission


   class ReportsChannelTests(TestCase):
       def test_staff_can_join_but_others_cannot(self):
           channel = ChannelPermission.objects.create(
               channel_name="reports",
               access=ChannelPermission.Access.STAFF_ONLY,
           )
           User = get_user_model()
           staff = User.objects.create_user("staff", is_staff=True)
           other = User.objects.create_user("other")

           self.assertTrue(channel.allows(staff))
           self.assertFalse(channel.allows(other))

.. _channel-permissions-future:

Planned changes
===============

.. important::

   The defaults described on this page keep existing projects working, and they are not the safest settings. They are planned to change in a future major version:

   * ``ALLOW_UNLISTED_CHANNELS`` will default to ``False``, so a channel without a rule is refused.
   * ``CHECK_PERMISSIONS_ON_CONNECT`` will default to ``True``, so ``permissions_required`` and ``all_permissions_required`` apply to the connect route.

   Each release that changes a default will say so in the :doc:`changelog`. To prepare, create an Allow all row for every channel you mean to keep public, create restricted rows for the rest, and set both attributes to the future values on your views now. Then you can check that every channel your clients use still works.
