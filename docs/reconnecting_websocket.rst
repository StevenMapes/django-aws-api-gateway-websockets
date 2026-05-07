Using reconnecting-websocket
============================

This guide shows how to setup the websockets to automatically reconnect from the client without using a 3rd part library.

Why use reconnecting websockets?
-------------------------------

Browser WebSocket connections can close for many reasons, including:

* temporary network loss;
* browser sleep or tab suspension;
* API Gateway timeouts;
* server restarts;
* mobile network changes.

The browser's built-in ``WebSocket`` class does not automatically reconnect.

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

This example shows creating a class to handle connection, token exchange, sending messages and reconnecting.

As this package supports grouping WebSocket sessions by channel the example also includes how to add the
``channel`` query string parameter to the WebSocket URL.

The server can then use the channel name to send messages to all active connections associated with that channel.


.. code-block:: html

   <script>
    window.myWebSocketConnected = false; /* Indicate that the websocket is not connected initially */
    const csrftoken = "";   // Fetch the CSRF token from the cookies OR set it here
    const wss_channel = "my-example-channel";


    class WebSocketManager {
        constructor(options) {
            this.wssUrl = options.wssUrl;
            this.tokenEndpoint = options.tokenEndpoint;
            this.channel = options.channel;
            this.routeKey = options.routeKey;
            this.reconnectDelay = options.reconnectDelay || 3000;
            this.tokenRetryDelay = options.tokenRetryDelay || 5000;
            this.socket = null;
        }

        /* Fetch the token */
        async getToken() {
            const request = new Request(
                this.tokenEndpoint,
                {headers: {'X-CSRFToken': csrftoken}, 'Content-Type': 'application/json'}
            );

            const response = await fetch(request, {method: "POST"});

            if (!response.ok) {
                throw new Error(`Unable to get WebSocket token: ${response.status}`);
            }

            const data = await response.json();
            return data.token;
        }

        /* Connect to the websocket */
        async connect() {
            let token;

            try {
                token = await this.getToken();
            } catch (error) {
                console.error(error);
                setTimeout(() => this.connect(), this.tokenRetryDelay);
                return;
            }

            const websocketUrl = (
                `${this.wssUrl}?ws_token=${encodeURIComponent(token)}` +
                `&channel=${encodeURIComponent(this.channel)}`
            );

            this.socket = new WebSocket(websocketUrl);

            this.socket.addEventListener("open", (event) => this.onOpen(event));
            this.socket.addEventListener("message", (event) => this.onMessage(event));
            this.socket.addEventListener("close", (event) => this.onClose(event));
            this.socket.addEventListener("error", (event) => this.onError(event));
        }

        {% comment %}Handle when a Websocket connection is made using a window var to ensure we only run the logic once{% endcomment %}
        onOpen(event) {
            if (window.myWebSocketConnected) {
                return;
            }
            if (window.OnWebSocketConnectFn) {
                /* You can define a callback function of payload to send to the server when the connection is established */
                this.send(window.OnWebSocketConnectFn);
            }
            if (window['myWsConnectionOpenWebhook']) {
                /* Support a callback function when the connection is established */
                window.myWsConnectionOpenWebhook();
            }
            window.myWebSocketConnected = true;
        }

        onMessage(event) {
            window.WebSocketNotSupported = false;
            const msg = JSON.parse(event.data);

            /* Do something with the message that was received from the server */
            console.log(msg);
        }

        /* On close automativally reconnect after a delay */
        onClose(event) {
            window.myWebSocketConnected = false;
            setTimeout(() => this.connect(), this.reconnectDelay);
        }

        onError(event) {
            console.error('WebSocket error:', event);
        }

        /* Method for sending messages across the websocket */
        send(handler, params = {}) {
            this.socket.send(JSON.stringify({
                "action": this.routeKey,
                "handler": handler,
                ...params
            }));
        }
    }

    const wmsWebSocketManager = new WebSocketManager({
        wssUrl: 'wss://{{ api_gateway_route.api_gateway.domain_name }}',
        tokenEndpoint: "{% url "websocket_token" %}",
        channel: wss_channel,
        routeKey: "{{ api_gateway_route.route_key }}"
    });

    /* Start to connect when the page is ready */
    document.addEventListener("DOMContentLoaded", function () {
        wmsWebSocketManager.connect();
    }
   </script>

Sending messages to Django
--------------------------

Messages sent from the browser should be JSON encoded.

By default, the ``action`` value is used by API Gateway as the route selection
key.

.. code-block:: html

   <script>
    wmsWebSocketManager.send("default", {message: "Hello from the browser"})
   </script>

If you have created a custom API Gateway route named ``notifications``, you can
send a message to that route like this:

.. code-block:: html

   <script>
       wmsWebSocketManager.send("notifications", {
           message: "Show this notification"
       });
   </script>

Sending a toast notification request
------------------------------------

A common pattern is to send a message to Django and then receive a message back
that the frontend displays as a toast.

Example browser message:

.. code-block:: javascript

   wmsWebSocketManager.send("default", {
       type: "toast",
       level: "success",
       message: "The browser is connected"
   });

Example frontend message handler:

.. code-block:: javascript

class CustomWebSocketManager extends WebSocketManager {
    onMessage(event) {
        // Call the parent implementation first (optional)
        super.onMessage(event);

        const message = JSON.parse(event.data);

        if (message.type === "toast") {
            this.showToast(message.level, message.message);
            return;
        }

       console.log("WebSocket message received:", message);
    }

    showToast(level, message) {
        console.log(`[${level}] ${message}`);
    }
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