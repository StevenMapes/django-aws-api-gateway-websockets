Clean-up
========

Overview
--------

WebSocket connections can disappear without always sending a clean disconnect
event. For example, a browser tab may close, a device may lose network access,
or API Gateway may remove a connection.

Because of this, applications should periodically clean up stale WebSocket
session records.

Why cleanup matters
-------------------

Cleaning up old sessions helps to:

* avoid sending messages to dead connections;
* reduce unnecessary API Gateway Management API calls;
* keep the session table smaller;
* improve multicast and broadcast performance;
* make operational debugging easier.

Stale connections
-----------------

A stale connection is a session that is no longer usable.

This may happen when:

* the client disconnects unexpectedly;
* API Gateway expires the connection;
* the connection is closed but the disconnect event is not processed;
* sending to the connection returns a gone or disconnected response.

Running cleanup manually
------------------------

Run the cleanup command manually with:

.. code-block:: console

   python manage.py clearWebSocketSessions

Scheduling cleanup
------------------

In production, run cleanup on a schedule.

Common options include:

* cron;
* systemd timers;
* Kubernetes CronJobs;
* ECS scheduled tasks;
* Heroku Scheduler;
* Celery Beat;
* a platform-specific scheduled job runner.

Suggested frequency
-------------------

The best frequency depends on your application traffic.

As a starting point, consider running cleanup every 5 to 15 minutes for busy
applications, or hourly for low-volume applications.

Cleaning up rate limit records
------------------------------

Rate limit checks use database records. Old records should be cleaned up
regularly to avoid unnecessary database growth.

The project includes a cleanup command for old WebSocket token and rate limit
records.

Run it manually with:

.. code-block:: console

   python manage.py cleanupWebSocketTokens

You can also pass cleanup options if supported by your installed version.

For example:

.. code-block:: console

   python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7

A common production approach is to run this command every few minutes using
cron, Celery Beat, a container scheduler, or your platform's scheduled task
system.

Example cron entry:

.. code-block:: text

   */5 * * * * cd /path/to/project && /path/to/venv/bin/python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7


Operational notes
-----------------

When sending multicast or broadcast messages, make sure your application handles
connections that have already gone away.

The cleanup process should be treated as a maintenance task, not as the only
line of defence against stale sessions.