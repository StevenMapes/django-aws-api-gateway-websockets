[![CI Build Status](https://img.shields.io/github/actions/workflow/status/StevenMapes/django-aws-api-gateway-websockets/main.yml?branch=main&style=for-the-badge)](https://github.com/StevenMapes/django-aws-api-gateway-websockets/actions)
[![Coverage](https://img.shields.io/badge/Coverage-96%25-success?style=for-the-badge)](https://github.com/StevenMapes/django-aws-api-gateway-websockets/actions?workflow=CI)
[![PyPi](https://img.shields.io/pypi/v/django-aws-api-gateway-websockets.svg?style=for-the-badge)](https://pypi.org/project/django-aws-api-gateway-websockets/)
![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge)
![Pre-Commit Enabled](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=for-the-badge)
[![Read The Docs](https://img.shields.io/readthedocs/django-aws-api-gateway-websockets?style=for-the-badge)](https://django-aws-api-gateway-websockets.readthedocs.io/)

[![PyPi Downloads](https://img.shields.io/pypi/dd/django-aws-api-gateway-WebSockets)](https://pypistats.org/packages/django-aws-api-gateway-WebSockets)

# Django AWS API Gateway Websockets
It is the aim of this project to create a uniform way to record websocket connections, associate the Django user who established the connection, and then retrieve that user within each request.

This project is designed to work exclusively with AWS API Gateway.

It is not intended to be a replacement for [Django Channels](https://github.com/django/channels). Instead, this project allows you to add [WebSockets](https://en.wikipedia.org/wiki/WebSocket) support to your project by writing normal HTTP request-response views whilst allowing [AWS API Gateway](https://aws.amazon.com/api-gateway/) to handle the WebSocket connection.

This project introduced a new [Class-Based-View](https://docs.djangoproject.com/en/dev/topics/class-based-views/) to handle connections, disconnections, routing, basic security checks and ensuring that the User object is available within every request.

The project will keep track of which users created which WebSockets, which ones are active and will allow you to send messages back down the socket to the client via Boto3.

Please refer to the installation notes and Getting Start Guides.

# Architecture and process flow
See the [Architecture](ARCHITECTURE.md) page.

# Getting Started

This project lets you handle AWS API Gateway WebSocket events from a Django view while keeping track of active connections and the Django user associated with each one.

## 1. Install the package
```bash
pip install django-aws-api-gateway-websockets
```

## 2. Add the app to `INSTALLED_APPS`
Add ```django_aws_api_gateway_websockets``` to ```INSTALLED_APPS```.

## 3. Configure AWS access

Choose one of the following options.

### Option A: IAM role / instance profile
If your app runs on AWS with an IAM role attached, set the region: ```AWS_GATEWAY_REGION_NAME = "eu-west-1"```

### Option B: Named AWS profile
If you use a local or shared AWS profile: ```AWS_IAM_PROFILE = "example"```

### Option C: Access key and secret
If you prefer explicit credentials:

```python 
AWS_ACCESS_KEY_ID = "My-Key-Here" 
AWS_SECRET_ACCESS_KEY = "My-Secret-Key-Here" 
AWS_GATEWAY_REGION_NAME = "eu-west-1"
```

## 4. Add a WebSocket URL route
Your URL pattern must include a `route` slug so API Gateway can pass through the route key.

```python
from django.urls import path from .views import ExampleWebSocketView

urlpatterns += [path("ws/<slug:route>", ExampleWebSocketView.as_view(), name="example_WebSocket")]
```

## 5. Create a WebSocket view
Subclass `WebSocketView` and implement the route methods you need.

```python
from django.http import JsonResponse
from django_aws_api_gateway_websockets.views import WebSocketView


class ExampleWebSocketView(WebSocketView):
    """Example WebSocket view."""
    
    def default(self, request, *args, **kwargs) -> JsonResponse:
        """Handle default messages."""
        action = self.body.get("action")
        return JsonResponse({"received": action})
```

## 6. Connect from the client
```javascript
const ws = new WebSocket("wss://ws.example.com?channel=my-example-channel");
ws.onmessage = function (event) { console.log(JSON.parse(event.data)); };
ws.send(JSON.stringify({ action: "default", message: "Hello from the browser" }));
```

## 7. Send a message back to the client
To send a response from the server, use the current `WebSocketSession`.

```python
self.websocket_session.send_message({ "type": "example", "message": "Hello from Django" })
```

## 8. Optional: create the AWS resources
If you are using the Django Admin integration, create the API Gateway record and then run the custom domain setup. If you are not using the admin UI, use the equivalent management commands instead.

---

# Restricting access to users
As of version 2.1.0 you can now use Django Permissions to restrict access to the methods that handle the WebSocket 
request within your views.py.

On the base view class there are two object properties that can be used to set the permissions that are required.

```has_any_permission``` -> User must have ANY of the permissions listed

```has_all_permission``` -> User must have ALL of the permissions listed

These checks will apply during the ```dispatch``` method and will return a 403 response if the user does not have the 
required permissions. Having permissions at an individual level is not currently supported automatically and will be 
added in a future release.

# Python and Django Support
This project only actively supports current Python and Django versions: Python 3.10-3.15, and Django 4.2, 5.1, 5.2 & 6.0.
It may work with other versions of Django from 4.2 up and Python 3.9+, but they are no longer tested.

| **Python/Django** | **4.2**  | **5.0** | **5.1**  | **5.2** | **6.0** |
|-------------------|----------|---------|----------|---------|---------|
| 3.9               | Y        | N/A     | N/A      | N/A     | N/A     |
| 3.10              | Y        | Y**     | Y        | Y       | N/A     |
| 3.11*             | Y        | Y**     | Y        | Y       | N/A     |
| 3.12              | Y        | Y**     | Y        | Y       | Y       |
| 3.13              | Y        | Y**     | Y        | Y       | Y       |
| 3.14              | N        | N       | Y        | Y       | Y       |
| 3.15              | N        | N       | Y        | Y       | Y       |

* *Python 3.11 only works with Django 4.1.3+
* **Django 5.0 is no longer being tested for support since May 2025 due to the final version having security issues

# Installation
You can install this package from pip using
```bash
pip install django-aws-api-gateway-WebSockets
```

## settings.py
Add ```django_aws_api_gateway_websockets``` to ```INSTALLED_APPS```.

### Decide on AWS Credential Setup
This package supports different ways to connect to AWS. Which option you require depends on the settings you need to define.

#### Using the IAM role of the instance
If you are running this package on an EC2 instance that has an IAM profile, then you only need to specify the region to connect to by setting ```AWS_GATEWAY_REGION_NAME``` in ```settings.py``` (falling back to ```AWS_REGION_NAME```).

E.G. ```AWS_GATEWAY_REGION_NAME="eu-west-1"``` will mean this package connects to the Ireland region using the IAM profile of the machine.

#### Named Profiles (AWS_IAM_PROFILE)
You can use a named profile by setting ```AWS_IAM_PROFILE``` to the name of the profile on your computer.

E.G. ```AWS_IAM_PROFILE="example"```. As the profile contains the region, you do not need to set anything else.

**NOTE:** If you are using ```Django-Storages```, you may already have set the value against ```AWS_S3_SESSION_PROFILE```.

#### Using AWS IAM Access Key and Secret
Alternatively you can specify the exact  ACCESS_KEY, SECRET_ACCESS_KEY and REGION_NAME you wish to use by setting the
three following ```settings.py``` values.

```
AWS_ACCESS_KEY_ID="My-Key-Here"
AWS_SECRET_ACCESS_KEY="My-Secret-Key-Here"
AWS_GATEWAY_REGION_NAME="region-to-use"
```

The order above is the recommended order to use. As with all custom Django settings it's advisable to store the real
values in either a secrets manager or environmental values. I tend to use https://pypi.org/project/python-decouple/

### IMPORTANT
If your site is **not** already running cross-origin you will need to update some settings and flush the sessions to ensure the primary domain and subdomain will work.

Because the API Gateway will run from a subdomain you need ensure the cookies are set-up to allow subdomains to read them.
Assuming your site runs from **www.example.com** and you wanted to use **ws.www.example.com** for WebSockets you would need to 
set the below CSRF and COOKIE settings (Django 4 examples shown)
```
# CSRF
CSRF_COOKIE_SAMESITE=Lax
# CSRF_TRUSTED_ORIGINS=www.example.com,ws.www.example.com ## For Django 3*
## For Django 4+
CSRF_TRUSTED_ORIGINS=https://www.example.com,https://ws.www.example.com
CSRF_COOKIE_DOMAIN='.www.example.com'

# Sessions
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_NAME='mysessionid'
SESSION_COOKIE_DOMAIN='.www.example.com'
```

If you wanted to use **www.example.com** for the main site and  **ws.example.com** for WebSockets you'd need to use 
these settings

```
# CSRF
CSRF_COOKIE_SAMESITE=Lax
CSRF_TRUSTED_ORIGINS=https://www.example.com,https://ws.www.example.com
CSRF_COOKIE_DOMAIN='.example.com'

# Sessions
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_NAME='mysessionid'
SESSION_COOKIE_DOMAIN='.example.com'
```

**NOTE:** You need to rename the SESSION cookie. In the example I have renamed if from ```sessionid``` to ```mysessionid```. This will ensure that any old cookies are ignored.

### Flushing Sessions
Because you are changing the session cookie you will also need to flush any cached sessions using: 

```bash
python manage.py clearsessions
```.

### Clearing Stale WebSocket connections
WebSocket connections can become stale over time, so some housekeeping is required. To help with this, there is a management command, ```clearWebSocketSessions```, that can be run to delete closed connections from the database. Simply run:

```bash
python manage.py clearWebSocketSessions
``` 
I recommend setting this as a scheduled task.

### Clean stable Tokens and Rate Limit
Ths management command ```cleanupWebSocketTokens``` will remove all expired tokens and rate limit tokens and should be
run frequently. We recommend running this command every 5 minutes.

```crontab
*/5 * * * * cd /path/to/project && python manage.py cleanupWebSocketTokens
```

# AWS Setup
In order for this package to create the API Gateway, it's routes, integration, custom domain and to publish messages
you will need to assign the correct permission to the IAM User/Role following best practices of restrictive permission.

If you are using a EC2/ECS then you should be using an IAM Role otherwise use a user.

This package **does not** include creating an AWS Certificate as you may already have one. You should create that 
yourself.  If you do not know how then see the [Appendix](#Appendix) section at the end of this file.

## IAM Policy
You'll need to grant the IAM permission to allow this project to create the API Gateway, create the domain mappings and
to execute the API to send messages from the server to the client(s).

I'm still reviewing the "minimum required permissions" but this project has been tested with the 
following IAM policy which you can copy and paste into the JSON editor within the AWS console:

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DjangoApiGatewayPolicy01",
            "Effect": "Allow",
            "Action": [
                "apigateway:GET",
                "apigateway:PATCH",
                "apigateway:POST",
                "apigateway:PUT",
                "execute-api:*",
                "iam:CreateServiceLinkedRole"
            ],
            "Resource": [
                "arn:aws:apigateway:*::/apis",
                "arn:aws:apigateway:*::/apis/*",
                "arn:aws:apigateway:*::/apis/*/authorizers",
                "arn:aws:apigateway:*::/apis/*/authorizers/*",
                "arn:aws:apigateway:*::/apis/*/cors",
                "arn:aws:apigateway:*::/apis/*/deployments",
                "arn:aws:apigateway:*::/apis/*/deployments/*",
                "arn:aws:apigateway:*::/apis/*/exports/*",
                "arn:aws:apigateway:*::/apis/*/integrations",
                "arn:aws:apigateway:*::/apis/*/integrations/*",
                "arn:aws:apigateway:*::/apis/*/integrations/*/integrationresponses",
                "arn:aws:apigateway:*::/apis/*/integrations/*/integrationresponses/*",
                "arn:aws:apigateway:*::/apis/*/models",
                "arn:aws:apigateway:*::/apis/*/models/*",
                "arn:aws:apigateway:*::/apis/*/models/*/template",
                "arn:aws:apigateway:*::/apis/*/routes",
                "arn:aws:apigateway:*::/apis/*/routes/*",
                "arn:aws:apigateway:*::/apis/*/routes/*/requestparameters/*",
                "arn:aws:apigateway:*::/apis/*/routes/*/routeresponses",
                "arn:aws:apigateway:*::/apis/*/routes/*/routeresponses/*",
                "arn:aws:apigateway:*::/apis/*/stages",
                "arn:aws:apigateway:*::/apis/*/stages/*",
                "arn:aws:apigateway:*::/apis/*/stages/*/accesslogsettings",
                "arn:aws:apigateway:*::/apis/*/stages/*/cache/authorizers",
                "arn:aws:apigateway:*::/apis/*/stages/*/routesettings/*",
                "arn:aws:apigateway:{AWS-REGION-NAME}::/domainnames",
                "arn:aws:apigateway:{AWS-REGION-NAME}::/domainnames/*/apimappings",
                "arn:aws:apigateway:{AWS-REGION-NAME}::/domainnames/*/apimappings/*",
                "arn:aws:execute-api:{AWS-REGION-NAME}:{AWS-ACCOUNT-NUMBER}:*/*/*/*",
                "arn:aws:iam::{AWS-ACCOUNT-NUMBER}:role/aws-service-role/ops.apigateway.amazonaws.com/AWSServiceRoleForAPIGateway"
            ]
        }
    ]
}
```

You will need to edit the permissions and replace the following: 
1. ```{AWS-REGION-NAME}``` with the correct AWS region you are using, E.G ```eu-west-1```. If you wish to grant access to all regions then replace this placeholder with an ```*```
2. ```{AWS-ACCOUNT-NUMBER}``` with your account number E.G: 123456789101 

This policy grants permissions to ensure the API Gateway(s) will be created, the custom domain name mapped to the 
gateway and that you can send messages from the server to clients.  The AWS Service role is required as it's used when 
you create a custom domain name for API Gateway. If you do this via the console it will create the role for you so we
need to ensure the IAM user has the permission in order to replicate this.

Once you have created your API Gateway(s) you may wish to follow AWS best practice and restrict of revoke the 
permissions to the API Gateway(s) you have created.  Because I do not know what you will name your gateway, the 
permissions above will allow you to add/edit and API gateway on your account.

# Getting Started

The core files within this project are:

1. ```django_aws_api_gateway_WebSockets.views.WebSocketView``` - The base class-based view from which you should extend
2. ```django_aws_api_gateway_WebSockets.models.ApiGateway``` - A model for managing the API Gateway. A Django Admin 
page is included along with custom actions to create the API Gateway and configure a Custom Domain.  For those with
projects not using Django Admin there are two management commands that perform the same actions. 
3. ```django_aws_api_gateway_WebSockets.models.WebSocketSession``` - The WebSocket session store. Every connection 
writes to this model which contains a method to send a message to the connection.  The QuerySet of the objects model 
manager has been extended to include a method to send messages to all records included within a queryset.  

## Django
### URLS.py
Edit your urls.py file and add an entry for the URL you wish API Gateway to call. **IMPORTANT** The slug parameter 
must be called "route". This will be populated by API Gateway with the route it uses E.G. $connect, $default or 
$disconnect

E.G. 
```
path("ws/<slug:route>", ExampleWebSocketView.as_view(), name="example_WebSocket")
```

### Creating the Views
Subclass the ```WebSocketView``` and implement methods where the name of the method is the name of the route the 
API Gateway has been setup to use. There are already methods for $connect and $disconnect you just need to implement
a method for ```default``` along with any other custom routes you have created.  The methods are selected dynamically
via the ```dispatch``` method with any leading dollar sign being removed.

The methods take the ```request``` parameter and only needs to return a response if you wish to return a negative HTTP
response such as a HttpResponseBadRequest otherwise there is no need to return anything.

```python
from django_aws_api_gateway_WebSockets.views import WebSocketView

class ExampleWebSocketView(WebSocketView):
    """Custom WebSocket view."""

    def default(self, request, *args, **kwargs) -> JsonResponse:
        """Add the logic you wish to make here when you receive a message.
         create your JSON response that you will handle within the Javascript
         """
        logger.debug(f"body {self.body}")

```

If you want to send a response to the WebSocket that made the request then you need to call the ```send_message()``` on
the WebSocketSession that is being used. See the example below

```python
from django_aws_api_gateway_WebSockets.views import WebSocketView

class ExampleWebSocketView(WebSocketView):
    """Custom WebSocket view."""

    def default(self, request, *args, **kwargs) -> JsonResponse:
        # Do stuff 
        ...        
        
        # Send a message back to the client - i.e unicast
        self.WebSocket_session.send_message({"key1": "value1", "key2": "value2"})

```

If you are using the "channels" to group WebSocket connections together for multicasting, that is one-to-many 
communication then you can use the following example

```python
from django_aws_api_gateway_WebSockets.models import WebSocketSession
from django_aws_api_gateway_WebSockets.views import WebSocketView


class ExampleWebSocketView(WebSocketView):
    """Custom WebSocket view."""

    def default(self, request, *args, **kwargs) -> JsonResponse:
        # Do stuff 
        ...        
        
        # Multicast a message to ALL CONNECTED clients on the same "channel"
        WebSocketSession.objects.filter(
            channel_name=self.WebSocket_session.channel_name
        ).send_message({"key": "value"})

        # Multicast a message to ALL CONNECTED clients who are with the 
        # channel_nme "my-example-channel"
        WebSocketSession.objects.filter(
            channel_name="my-example-channel"
        ).send_message(
            {
                "key": "value"
            }
        )

```

#### Using the Route Selection Key value to call specific methods
API Gateway works by routing messages based on the "Route Selection Key". This project sets you up with a default route
so that you have a catch-all route but the Route Selection Key is preserved and is used by the dispatch method when 
selecting the method to use to handle the request.  This means that you can write individual methods to handle each 
route individually for cleaner, more testable code.

In the example that follows the default Route Selection Key of **action** is being used. 
Assume that two series of sends are made to the WebSocket. The first with the payload: 
```{"action": "test", "value": "hello world"}``` and the second ```{"action": "help", "value": "Help Me"}```. You can
either handle these within the catch-all ```default``` method or you can write individual methods for each action

```python
from django_aws_api_gateway_WebSockets.models import WebSocketSession
from django_aws_api_gateway_WebSockets.views import WebSocketView


class ExampleWebSocketView(WebSocketView):
    """Custom WebSocket view."""

    def test(self, request, *args, **kwargs) -> JsonResponse:
        print(self.body.get("value"))
        # Prints "hello world" 

    def help(self, request, *args, **kwargs) -> JsonResponse:
        print(self.body.get("value"))
        # Prints "Help Me" 
```

**Remember**: The "action" key is the default ```route_selection_key```, if you chose to use a different one when 
setting up the WebSocket make sure to update the ```route_selection_key``` class property to use the same value


### Debugging the View
Sometimes you the view may return a HTTP400 that you wish to debug further. In order to help with this you can pass
```debug=True``` into the ```as_view()``` method. The class will then call the private method ```_debug(msg)``` passing
in a string. By default this method will update a list property called ```debug_log``` with the message string but 
you may wish to simply overload the method and call your logger.

E.G.
```python
def _debug(self, msg: str):
    if self.debug:
        logger.debug(msg)
```

This can help track the issue which may be as simply as sending a message from the client that is missing the 
```route_select_key```.

## Example of sending a message from the server to the client
To send a message to a specific connection simple load its ```WebSocketSession``` record and then call the 
```send_message``` method passing in a JSON compatible dictionary of the payload you wish to send to the client.

### Sending a message to one connection
```python
from django_aws_api_gateway_WebSockets.models import WebSocketSession

obj = WebSocketSession.objects.get(pk=1)
obj.send_message({"type": "example", "msg": "This is a message"})
```

### Sending a message to ALL active connections associated with the same channel 
```python
from django_aws_api_gateway_WebSockets.models import WebSocketSession

WebSocketSession.objects.filter(channel_name="Chatroom 1").send_message(
    {"msg": "This is a a sample message"}
)
```

The ```WebSocketSessionQuerySet.send_message``` method automatically adds a filter of ```connected=True``` 

## Django Admin
Three Django Admin pages will be added to your project under the app _Django AWS APIGateway WebSockets_. Those pages 
allow you to view and manage the three base models.

### Creating an API Gateway Endpoint
**Important:** This section assumes that you are using an IAM account with the permissions listed earlier.

Using the Django Admin page, create a new API Gateway record using the following reference:

1. **API Name** - The human-friendly API name
2. **API Description** - Optional
3. **Default channel name** - Fill this in if you want all connections to this WebSocket to also be associated with the same "channel"; otherwise leave it blank. "Channels" are groups of WebSocket connections and nothing more.
4. **Target base Endpoint** - This is the full URL path to the view you wish to use to handle the requests, excluding the ```route``` slug portion that will be automatically appended.
5. **Certificate ARN** - You'll need to manually create a certificate within AWS. Once you have one, copy the ARN into this field.
6. **Hosted Zone ID** - If you use Route53, enter the Hosted Zone ID here if you wish to use a custom domain name with the API Gateway Endpoint.
7. **API Key Selection Expression** - In most cases, leave this as the default value. See the AWS docs for more.
8. **Route selection expression** - As above. This is the field that maps the "action" key within the payload as the key used to determine the route to take. If you change this, you must override the ```route_selection_key``` of the view.
9. **Route key** - This is the default root key. In most cases you will not need to change this.
10. **Stage Name** - The name you wish to give to the stage. Currently this package does not support multiple stages. If you leave it blank, it will default to "production".
11. **Stage description** - Optional
12. **Tags** - Currently not implemented, but these will be used to create the tags with AWS.
13. **API ID** - This will be populated when the API is created.
14. **API Endpoint** - This will be populated when the API is created.
15. **API Gateway Domain Name** - This will be populated when you run the Custom Domain setup. The value that appears here is the value your DNS CNAME entry should point to.
16. **API Mapping ID** - This will be populated when the API is created.

Once you have created the record within the database simply select it from the Django Admin list view, choose 
**Create API Gateway** action from the actions list and click Go.  The API Gateway record will be created within your
account. When it's ready the "API Created" column will show as True.

Once the API has been created you can now add a custom domain name mapping by choosing the row again and this time 
selecting the **Create Custom Domain record for the API**. This will create the Custom Domain record and will associate
it with the stage name you entered earlier. Once it's completed the **Custom Domain Created** flag will be set as True.

At this point you can open the record where you'll find that the ```API Gateway Domain Name``` has been populated.

## Django Management Commands
If you are not using Django Admin then you can populate the apigateway database table manually using the same list 
as shown above.

Once you've populated those fields you can then run the two actions as management commands rather than via Django Admin.

```
python manage.py createApiGateway --pk=1
```

```
python manage.py createCustomDomain --pk=1
```

The same actions will run as above.

## Adding Additional Routes
This project will route all requests to one URL by default however that is not always what you will need, 
sometimes you will want to route requests to different URLs to send requests to different views potentially within 
different apps.  API Gateway support this by using _"integrations"_ and _"routes"_ that use unique "route keys" to 
identify requests and then route those requests to a URL.

To support this approach this project uses the ```ApiGatewayAdditionalRoute``` model entries to map a route key to a chosen URL.
They are available to manage as inline forms on the main ```ApiGateway``` admin or as their own admin page.

The models are set-up to auto-deploy the new route if the ```ApiGateway``` has already been deployed. If it has not been
deployed already then these routes will be setup during the main deployment.

From the client side you choose the route you wish to take by setting the value of the **action** to the route key you
wish to match.


## Gotchas and debugging
### Failure to connect to WebSockets
#### Differing required headers
The most common reasons for the WebSocket failing to connect is due to different required headers. The base view is 
set-up with two lists of expected headers. ```required_headers``` and ```additional_required_headers```. If you are 
deploying to an EC2 server then you shouldn't have to change these but if you are deploying elsewhere or are testing
locally you may find that you need to change some of these. During development of this library I was using an
[NGROK](https://ngrok.com/) network edge tunnel and found that the "X-Real-Ip" and "Connection" headers were being lost
during which is why they were moved to the additional_required_headers. If you find this is the case for you then simply
overload the class property and set it to an empty list.


# Client Side Integration (Javascript)
This section will guide you through connecting to and using this project from a webpage.

## Security: CSRF Protection with WebSocket Tokens (Version 3.0+)

**Important:** As of version 3.0, WebSocket connections require a one-time use token for CSRF protection. This token 
must be obtained before establishing the WebSocket connection.
That is unless you turn off the use of tokens

### Step 1: Add the Token Generation URL

Add the `WebSocketTokenView` to your `urls.py`:

```python
from django.urls import path
from django_aws_api_gateway_websockets.views import WebSocketTokenView

urlpatterns = [
    # ... your other URLs ...
    path('api/ws-token/', WebSocketTokenView.as_view(), name='websocket_token'),
]
```

### Step 2: Client-Side Token Retrieval and Connetion
Using Fetch API and Reconnecing Websocket

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js" 
        integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA==" 
        crossorigin="anonymous" 
        referrerpolicy="no-referrer"></script>
<script>
    // Configuration
    const WS_BASE_URL = 'wss://ws.example.com';
    const CHANNEL_NAME = 'my-example-channel';
    const TOKEN_ENDPOINT = '/api/ws-token/';
    
    let exampleWS = null;
    
    // Function to get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    
    // Function to fetch a new WebSocket token
    async function getWebSocketToken() {
        const csrfToken = getCookie('csrftoken');
        
        try {
            const response = await fetch(TOKEN_ENDPOINT, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin'  // Include cookies
            });
            
            if (!response.ok) {
                throw new Error(`Token request failed: ${response.status}`);
            }
            
            const data = await response.json();
            return data.token;
        } catch (error) {
            console.error('Failed to get WebSocket token:', error);
            return null;
        }
    }
    
    // Function to connect or reconnect the WebSocket
    async function connectWebSocket() {
        const token = await getWebSocketToken();
        
        if (!token) {
            console.error('Could not obtain WebSocket token');
            // Retry after 5 seconds
            setTimeout(connectWebSocket, 5000);
            return;
        }
        
        // Build WebSocket URL with token and channel
        const wsUrl = `${WS_BASE_URL}?ws_token=${token}&channel=${encodeURIComponent(CHANNEL_NAME)}`;
        
        // Create ReconnectingWebSocket instance
        exampleWS = new ReconnectingWebSocket(wsUrl, null, {
            debug: false,
            reconnectInterval: 3000,
            maxReconnectInterval: 10000,
            reconnectDecay: 1.5,
            timeoutInterval: 5000,
            maxReconnectAttempts: null  // Retry indefinitely
        });
        
        exampleWS.onopen = function(event) {
            console.log('WebSocket connected');
        };
        
        exampleWS.onmessage = function(event) {
            console.log('Message received:', event.data);
            const msg = JSON.parse(event.data);
            // Handle your message here
            console.log('Parsed message:', msg);
        };
        
        exampleWS.onerror = function(event) {
            console.error('WebSocket error:', event);
        };
        
        exampleWS.onclose = function(event) {
            console.log('WebSocket closed:', event.code, event.reason);
            
            // If the token expired (close code could be 1000 or 1006), get a new token
            // The ReconnectingWebSocket library will handle reconnection
            // but we need to get a fresh token
            setTimeout(async () => {
                if (exampleWS.readyState === WebSocket.CLOSED || 
                    exampleWS.readyState === WebSocket.CLOSING) {
                    exampleWS.close();  // Ensure it's fully closed
                    await connectWebSocket();  // Get new token and reconnect
                }
            }, 3000);
        };
    }
    
    // Function to send messages
    function sendMessage(action, data) {
        if (exampleWS && exampleWS.readyState === WebSocket.OPEN) {
            exampleWS.send(JSON.stringify({
                action: action,
                ...data
            }));
        } else {
            console.error('WebSocket is not connected');
        }
    }
    
    // Initialize connection when page loads
    document.addEventListener('DOMContentLoaded', function() {
        connectWebSocket();
    });
    
    // Example: Send a message
    // sendMessage('custom', { message: 'Hello from the browser' });
</script>
```

### Important Notes:
1. **Token Expiration:** Tokens expire after 60 seconds. The connection must be established within this time.
2. **Token Reuse:** Tokens are single-use only. Each new connection requires a fresh token.
3. **Reconnection Strategy:** When the WebSocket disconnects, always fetch a new token before reconnecting.
4. **Rate Limiting:** Token generation is rate-limited to 10 tokens per minute per user by default.
5. **Authentication:** The token endpoint requires user authentication. Ensure users are logged in.

## Legacy Integration (Pre-3.0)
If you're using version 2.x or have disabled token authentication (USE_WS_TOKEN = False), you can connect directly:

### Basic Integration
Below is a very basic integration using the WebSockets API built into browsers. It does not handle reconnecting dropped
WebSockets, see the next section for that.

**WARNING**: This method will create a WebSocket that will timeout after around 10 minutes. 

The below example assumes you created the API Gateway to work on the custom domain name ws.example.com
```javascript
let wss_url = 'wss://ws.example.com';
let regDeskWSocket = new WebSocket(wss_url);
regDeskWSocket.onmessage = function(event) {
    // Take your action here to handle messages being received
    console.log(event);
    let msg = JSON.parse(event.data);
    console.log(msg);
};
```

You can set the channel by using the **channel** querystring parameter during the connection 

```javascript
let wss_url = 'wss://ws.example.com?channel=my+example+channel';
let exampleWS = new WebSocket(wss_url);
exampleWS.onmessage = function(event) {
    // Take your action here to handle messages being received
    console.log(event);
    let msg = JSON.parse(event.data);
    console.log(msg);
};
```

### Reconnecting WebSockets
WebSockets can disconnect due to a variety of reasons; to work around this here are some links to libraries of proposed
solutions:

1. [Stack Overflow- WebSocket: How to automatically reconnect after it dies](https://stackoverflow.com/questions/22431751/WebSocket-how-to-automatically-reconnect-after-it-dies)
2. [JS library - reconnecting-WebSocket](https://github.com/joewalnes/reconnecting-WebSocket)

The below example is using the JS library. Note you just include the lib and then use the 
```ReconnectingWebSocket``` class rather than ```WebSocket```:

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-WebSocket/1.0.0/reconnecting-WebSocket.min.js" integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<script>
let wss_url = 'wss://ws.example.com';
let exampleWS = new ReconnectingWebSocket(wss_url);
exampleWS.onmessage = function(event) {
    // Take your action here to handle messages being received
    console.log(event);
    let msg = JSON.parse(event.data);
    console.log(msg);
};
</script>
```

### Sending a message from the client to the server
Both the example above use the same method.

```javascript
let wss_url = 'wss://ws.example.com?channel=my+example+channel';
let exampleWS = new WebSocket(wss_url);  // Or use ReconnectingWebSocket it does not matter

// Send a message
exampleWS.send(JSON.stringify({"action": "custom", "message": "What is this"}))
```

**IMPORTANT** The value of ```action``` determines the route that is used by **API Gateway**. By default, the only 
routes that are set-up are ```$connect```, ```$disconnect``` and ```default```. Any messages sent to unknown routes on 
the API Gateway are delivered to the ```default``` route.  So if you created a custom route called ```bob``` and then 
sent the following message from the client:

```
exampleWS.send(JSON.stringify({"action": "bob", "message": "What is this"}))
```

API Gateway will route this to the endpoint set for the "bob" route. This will be calling your view with the route slugs
value being assigned to **bob**. The ```dispatch``` method of the view will then look for a method on the class called
```bob```. If one is found then it will be invoked otherwise the ```default``` method will be called.

## Automated Cleanup (Version 3.0+)

To prevent database bloat from expired tokens and old rate limit records, schedule the cleanup management command:

### Using Cron

```bash
# Run every 5 minutes
*/5 * * * * cd /path/to/project && /path/to/venv/bin/python manage.py cleanupWebSocketTokens --token-age=300 --rate-limit-age=7
```

### Using Django-Celery-Beat

```python
# In your settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'cleanup-websocket-tokens': {
        'task': 'yourapp.tasks.cleanup_websocket_data',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
}

# In yourapp/tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def cleanup_websocket_data():
    call_command('cleanupWebSocketTokens', '--token-age=300', '--rate-limit-age=7')
```

---

# 🔒 SECURITY FEATURES IMPLEMENTED (v3.0.0 onwards)
## Defense in Depth
1. Authentication Layer
  - User authentication required for token generation
  - Session validation
2. Authorization Layer
  - Django permissions support (has_any_permission, has_all_permission)
  - Method-level access control via ALLOWED_HANDLERS and ADDITIONAL_ALLOWED_HANDLERS for extending automatic access
3. Input Validation Layer
  - Request body size limits (128KB)
  - JSON parsing with error handling
  - Connection ID validation
  - Channel name validation
  - IP address validation
  - Domain name validation
  - Message size validation
  - Rate Limiting Layer
  - Token generation rate limiting (10/min per user)
  - Connection attempt rate limiting (20 per 5min per IP/user)
  - Configurable thresholds
4. CSRF Protection Layer
  - One-time WebSocket tokens
  - Session-bound validation
  - Time-limited tokens (60s)
  - Atomic single-use enforcement
5. Audit & Monitoring Layer
  - Admin action logging
  - Connection attempt tracking
  - Debug mode with sanitized output
6. Error Handling Layer
  - Generic error messages to users
  - Detailed logging for administrators
  - No stack trace exposure

## COMPLIANCE STATUS
OWASP Top 10 (2021)
- ✅ A01:2021 - Broken Access Control - MITIGATED (permissions + ALLOWED_HANDLERS)
- ✅ A02:2021 - Cryptographic Failures - N/A (uses Django/AWS crypto)
- ✅ A03:2021 - Injection - MITIGATED (input validation + parameterized queries)
- ✅ A04:2021 - Insecure Design - MITIGATED (defense in depth)
- ✅ A05:2021 - Security Misconfiguration - MITIGATED (secure defaults)
- ✅ A06:2021 - Vulnerable Components - N/A (depends on user's Django/Python versions)
- ✅ A07:2021 - Identification/Authentication Failures - MITIGATED (CSRF tokens)
- ✅ A08:2021 - Software/Data Integrity - MITIGATED (single-use tokens)
- ✅ A09:2021 - Security Logging Failures - MITIGATED (comprehensive logging)
- ✅ A10:2021 - Server-Side Request Forgery - N/A (not applicable)

## Why the CSRF Excempt Decorator?
The ```csrf_exempt``` decorator is now required on the base view class.
**IMPORTANT:**: In order for the dispatch method to work it requires the ```csrf_exempt``` decorator to be added. This has
already been added as a class decorator on the base view, if you overload the dispatch method you will need to add
it back to avoid receiving CSRF Token failures. Due to this the project implements support for a short-lived 
"websocket token" that should be generated and sent with the connection request. The token is request with the CSRF
Token in order to validate the user, then the returned token is used within the WS connection request to ensure the
user is authenticated and is the same user. It's short lived so connection requests shold be made as soon as the token
is fetched. You can disabled the use of the tokens by turning off the ```USE_WS_TOKEN``` within the WebSocketView class.

This project also supports rate-limiting with the default allowing 20 connection attempts per 5 minute per user. You can configure
the thresholds by setting the ```RATE_LIMIT_ENABLED``` and ```RATE_LIMIT_MAX_ATTEMPTS``` 
and ```RATE_LIMIT_WINDOW_MINUTES``` within the WebSocketView class.

---

# Appendix

## Creating an SSL Certificate within AWS Certificate Manager
Please refer to the [official AWS documentation](https://docs.aws.amazon.com/acm/latest/userguide/gs-acm-request-public.html)

# Found a Bug?
Issues are tracked via GitHub issues at the [project issue page](https://github.com/StevenMapes/django-aws-api-gateway-WebSockets/issues)

# Have A Feature Request?
Feature requests can be raised by creating an issue within the [project issue page](https://github.com/StevenMapes/django-aws-api-gateway-WebSockets/issues), but please create the issue with "Feature Request -" at the start of the issue

# Testing
To run the tests use

```
coverage erase && \
python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings && \
coverage combine && \
coverage report
```

# Compiling Requirements
Run ```pip install pip-tools``` then run ```python requirements/compile.py``` to generate the various requirements files.
I use two local VIRTUALENVS to build the requirements, one running Python3.8 and the other running Python 3.11.

Also require ```pytest-django``` for testing

# Building
This project uses hatchling
```python -m build --sdist```

# tox

# Contributing
- [Check for open issues](https://github.com/StevenMapes/django-aws-api-gateway-WebSockets/issues) at the project issue page or open a new issue to start a discussion about a feature or bug.
- Fork the [repository on GitHub](https://github.com/StevenMapes/django-aws-api-gateway-WebSockets) to start making changes.
- Clone the repository
- Initialise pre-commit by running ```pre-commit install```
- Install requirements from one of the requirement files depending on the versions of Python and Django you wish to use.
- Add a test case to show that the bug is fixed or the feature is implemented correctly.
- Test using ```python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings```
- Create a pull request, tagging the issue, bug me until I can merge your pull request. Also, don't forget to add yourself to AUTHORS.
