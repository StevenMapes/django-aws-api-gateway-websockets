.. Django-AWS-API-Gateway-Websockets documentation master file, created by
   sphinx-quickstart on Tue Oct 19 20:17:02 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Django-AWS-API-Gateway-Websockets' documentation!
=============================================================

Django-AWS-API-Gateway-Websockets was designed to allow rapid integration of Django Class-Base-Views as HTTP(S) backends
for AWS API Gateway Websocket APIs without having to concern yourself with setting up and maintaining a WebSocket server.

If you are looking for fully-fledged WebSockets servers then take a look at Django-Channels.

If you want to introduce WebSockets to your project, you use or are happy to use Amazon Web Services, but do not have
time or want/ learn how websockets work then this is the project for you. It will enable you to create normal HTTP
endpoints that return ``JSONResponses`` objects rather than ``HttpResponse`` objects and leave the rest up to AWS Api
Gateway, for the Websocket side, and this project to ensure the ``User`` is available within each request object.

If you are not familiar with `Django's Class-base Views <https://docs.djangoproject.com/en/3.2/topics/class-based-views/>`_
then do follow that link and read up first of all.
You will also find the reference site `Classy Class-Based Views <https://ccbv.co.uk/>`_ extremely useful.

This project subclasses Django's generic ``View`` class and implements methods for each API Gateway route you define.

To get started see the :doc:`installation` section. Otherwise, take your pick:

.. toctree::
   :maxdepth: 2

   installation
   views
   models
   aws integration
   contributing
   history


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
