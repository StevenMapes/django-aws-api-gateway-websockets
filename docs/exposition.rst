Exposition
==========

This page gives a short overview of the main functionality provided by
Django-AWS-API-Gateway-WebSockets.

Receiving messages
------------------

Incoming WebSocket events from AWS API Gateway are routed to Django views.

The base WebSocket view validates the request, identifies the API Gateway and
connection, records or updates the WebSocket session, and then dispatches the
event to the appropriate handler.

Typical WebSocket lifecycle events include:

* connection;
* disconnection;
* default messages;
* custom route messages.

Sending a message in reply
--------------------------

A view handling a WebSocket message can send a response back to the connection
that made the request.

This is useful for request/response-style WebSocket interactions, such as:

* confirming that an action was received;
* returning validation errors;
* sending the result of a server-side action;
* acknowledging subscription or channel changes.

Multicasting
------------

Connections can be grouped by channel name.

Multicasting allows the application to send a message to every active connection
within a selected channel. This is useful when several clients are subscribed to
the same logical stream of updates.

Example use cases include:

* notifying all viewers of a page that new data is available;
* sending updates to members of a room, group, or dashboard;
* pushing live changes to users watching the same resource.

Broadcasting
------------

Broadcasting is the process of sending a message to a wider set of connected
sessions.

Depending on how your application models channels and sessions, a broadcast may
target:

* all active sessions;
* all sessions for a specific API Gateway;
* all sessions matching a queryset or filter;
* all sessions in one or more application-defined channels.

Sending toasts
--------------

Toast notifications are a common use case for WebSockets.

A server-side action can send a small message to the browser, where frontend
JavaScript displays it as a notification.

Typical toast payloads might include:

* a message;
* a severity such as ``success``, ``info``, ``warning``, or ``error``;
* an optional title;
* an optional timeout;
* optional metadata used by the frontend.

For example, your frontend may receive a WebSocket message and display a toast
when a background task completes, when a record changes, or when an error needs
to be shown to the user.