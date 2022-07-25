[![Read The Docs](https://img.shields.io/readthedocs/django-mysql?style=for-the-badge)](https://django-aws-api-gateway-websockets.readthedocs.io/)
![CI Build Status](https://img.shields.io/github/workflow/status/StevenMapes/django-aws-api-gateway-websockets/CI/main?style=for-the-badge)
![Coverage](https://img.shields.io/codecov/c/github/StevenMapes/django-aws-api-gateway-websockets/main?style=for-the-badge)

# Django AWS API Gateway Websockets
It is the aim of this project to create a uniform way to record websocket connections, associate the Django user who established the connection and then retrieve that user within each request.

This project is designed to work exclusively with AWS API Gateway.

It is not intended to be a replacement of [Django Channels](https://github.com/django/channels) instead this project allows you to add [WebSockets](https://en.wikipedia.org/wiki/WebSocket) support into your project by writing normal HTTP request-response views whilst allowing [AWS API Gateway](https://aws.amazon.com/api-gateway/) to worry about the WebSocket connection.

This project introduced a new [Class-Based-View](https://docs.djangoproject.com/en/dev/topics/class-based-views/) to handle connections, disconnections, routing, basic security checks and ensuring that the User object is available within every request.

The project will keep track of which users created which WebSockets, which ones are active and will allow you to send messages back down the socket to the client via Boto3.

Please refer to the installation notes and Getting Start Guides.

# Security Concerns
**IMPORTANT:**: In order to work the dispatch method requires the ```csrf_exempt``` decorator to be added.

# Python and Django Support
This project officially supports Python 3.8+ and Django 3.2+.

# AWS Setup
In order for this package to create the API Gateway, it's routes, integration, custom domain and to publish messages
you will need to assign the correct permission with your IAM User or Role following best practices.

If you are using a EC2/ECS then you should be using an IAM Role. 

## IAM Permissions
**IMPORTANT**: I'm still reviewing the "minimum required permissions" but this project has been tested with the 
following:

1. GET, POST, PATCH and PUT permissions to the API Gateway restricted to the API ID of the API Gateway you created above.
2. __execute-api__ which is used to send messages again restricted.

The IAM role requires both the POST permission to ```apigateway``` and ```apigateway2```, you may want to grant GET 
as well so you can use the client.get_domain_names() method.
```
{
    "Sid": "VisualEditor7",
    "Effect": "Allow",
    "Action": [
        "apigateway:GET",
        "apigateway:POST"
    ],
    "Resource": "arn:aws:apigateway:REGION_NAME_HERE::/domainnames"
}
```
Ensure the action ```"execute-api:*"``` is granted to the resource of
```
"arn:aws:execute-api:REGION_NAME:YOUR_AWS_ACCOUNT_ID_HERE:*/*/*/*"
``` 
where the REGION_NAME is the region you expect
or * and YOUR_AWS_ACCOUNT_ID_HERE is your account id

# Installation
You can install this package from pip using
```
pip install django-aws-api-gateway-websockets
```

## settings.py
Add ```django_aws_api_gateway_websockets``` into ```INSTALLED_APPS``` 

Because the API Gateway will run from a subdomain you need to make sure your cookies are setup to allow subdomains.
Assuming your site runs from www.example.com and you wanted to use ws.www.example.com for websockets you would need to 
set the below
```
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_DOMAIN='.www.example.com'
CSRF_COOKIE_DOMAIN='.www.example.com'
```

# Getting Started

The core files within this project are:

1. ```django_aws_api_gateway_websockets.views.WebSocketView``` - The base class-based view from which you should extend
2. ```django_aws_api_gateway_websockets.models.ApiGateway``` - A model for managing the API Gateway. A Django Admin 
page is included along with custom actions to create the API Gateway and configure a Custom Domain.  For those with
projects not using Django Admin there are two management commands that perform the same actions. 
3. ```django_aws_api_gateway_websockets.models.WebSocketSession``` - The websocket session store. Every connection 
writes to this model which contains a method to send a message to the connection.  The QuerySet of the objects model 
manager has been extended to include a method to send messages to all records included within a queryset.  

## Django
### URLS.py
Edit your urls.py file and add an entry for the URL you wish API Gateway to call. **IMPORTANT** The slug parameter 
must be called "route". This will be populated by API Gateway with the route it uses E.G. $connect, $default or 
$disconnect

E.G. 
```
path("ws/<slug:route>", ExampleWebSocketView.as_view(), name="example_websocket")
```

### Creating the Views
Subclass the ```WebSocketView``` and implement methods where the name of the method is the name of the route the 
API Gateway has been setup to use. There are already methods for $connect and $disconnect you just need to implement
a method for ```default``` along with any other custom routes you have created.  The methods are selected dynamically
via the ```dispatch``` method with any leading dollar sign being remove.

The methods take the ```request``` parameter and must return a ```JSONResponse``` but otherwise you are free to take
whatever action you require.

```
from django_aws_api_gateway_websockets.views import WebSocketView

class ExampleWebSocketView(WebSocketView):
    """Custom Websocket view."""

    def default(self, request, *args, **kwargs) -> JsonResponse:
        """Add the logic you wish to make here when you receive a message.
         create your JSON response that you will handle within the Javascript
         """
        
        logger.debug(f"body {self.body}")
        
        return JsonResponse({})
```

## Example of sending a message from the server to the client
To send a message to a specific connection simple load its ```WebSocketSession``` record and then call the 
```send_message``` method passing in a JSON compatible dictionary of the payload you wish to send to the client.

### Sending a message to one connection
```python
from django_aws_api_gateway_websockets.models import WebSocketSession

obj = WebSocketSession.objects.get(pk=1)
obj.send_message({"type": "example", "msg": "This is a message"})
```

### Sending a message to ALL active connections associated with the same channel 
```python
from django_aws_api_gateway_websockets.models import WebSocketSession

WebSocketSession.objects.filter(channel_name="Chatroom 1").send_message(
    {"msg": "This is a a sample message"}
)
```

The ```WebSocketSessionQuerySet.send_message``` method automatically adds a filter of ```connected=True``` 

## Django Admin
Two Django Admin pages will be available within your project under the app _Django AWS APIGateway WebSockets_.

Those pages allow you to view and manage the two base models.

### Creating an API Gateway Endpoint
**Important** This section assumes that you have created the IAM access required.

Using the Django Admin page create a new API Gateway record using the following for reference:

1. **API Name** - The human friendly API Name
2. **API Description** - Optional
3. **Default channel name** - Fill this in if you want all connections to this Websocket to also be associated with 
the same "channel" otherwise leave it blank. "Channels" are groups of web socket connections and nothing more.
4. **Target base Endpoint** - This is the full URL path to the view you wish to use to handle the requests **excluding**
the ```route``` slug portion that will be automatically appended.
5. **Certificate ARN** - You'll need to manually create certificate within AWS. Once you have, copy the ARN into this field
6. **Hosted Zone ID** - If you use Route53 then you'll need to enter the Hosted Zone ID here if you wish to use a custom
domain name with the API Gateway Endpoint
7. **API Key Selection Expression** - In most cases leave this as the default value. See the AWS docs for more
8. **Route selection expression** - As per the above. This is the field that maps the "action" key within the payload 
as being the key to determine the route to take.  If you change this then you must overload the 
```route_selection_key``` of the view
9. **Route key** - This is the default root key. In most cases you will not need to change this.
10. **Stage Name** - The name you wish to give to the staging. Currently this package does not support multiple stages.
If you leave it blank it will default to "production"
11. **Stage description" - Optional
12. **Tags** - Currently not implement but these will be used to create the tags with AWS
13. **API ID** - This will be populated when the API is created.
14. **API Endpoint** - This will be populated when the API is created.
15. **API Gateway Domain Name** - This will be populated when you run the Custom Domain setup. The value that appears 
here is the value to which you should your DNS CNAME entry should point. 
16. **API Mapping ID** - This will be populated when the API is created.

Once you have create the record within the database simply select it from the Django Admin list view, choose 
**Create API Gateway** action from the actions list and click Go.  The API Gateway record will be created within your
account. When it's ready the "API Created" column will show as True.

Once the API has been created you can now add a custom domain name mapping by choosing the row again and this time 
selecting the **Create Custom Domain record for the API**. This will create the Custom Domain record and will associate
it with the stage name you entered earlier. Once it's completed the **Custom Domain Created** flag will be set as True.

At this point you can open the record where you'll find that the ```API Gateway Domain Name``` has been populated.

## Django Management Commands
If you are not using Django Admin then you can populate the apigateway database table manually using the same list 
as shown above.

Once you've populated those fields you an then run the two actions as management commands rather than via Django Admin.

```python manage.py createApiGateway --pk=1```

```python manage.py createCustomDomain --pk=1```

The same actions will run as above.

# Client Side Integration (Javascript)
This section will guide you through two common ways of connecting to and using this project from a webpage.

### Basic Integration
Below is a very basic integration using the WebSockets API built into browsers. It does not handle reconnecting dropped
websockets, see the next section for that.

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
Websockets can disconnect due top a variety of reasons to work around this here are some links to libraries of proposed
solutions

1. [Stack Overflow- WebSocket: How to automatically reconnect after it dies](https://stackoverflow.com/questions/22431751/websocket-how-to-automatically-reconnect-after-it-dies)
2. [JS library - reconnecting-websocket](https://github.com/joewalnes/reconnecting-websocket)

The below example is using the JS library. Note you just include the lib and then use the 
```ReconnectingWebSocket``` class rather than ```WebSocket```:



```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/reconnecting-websocket/1.0.0/reconnecting-websocket.min.js" integrity="sha512-B4skI5FiLurS86aioJx9VfozI1wjqrn6aTdJH+YQUmCZum/ZibPBTX55k5d9XM6EsKePDInkLVrN7vPmJxc1qA==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
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

# Found a Bug?
Issues are tracked via GitHub issues at the [project issue page](https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues)

# Have A Feature Request?
Feature requests can be raised by creating an issue within the [project issue page](https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues), but please create the issue with "Feature Request -" at the start of the issue

# Documentation
TBA

# Compiling Requirements
Run ```pip install pip-tools``` then run ```python requirements/compile.py``` to generate the various requirements files
Also require ```pytest-django``` for testing

# Testing

# pip-tools

# tox

# Contributing
- [Check for open issues](https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues) at the project issue page or open a new issue to start a discussion about a feature or bug.
- Fork the [repository on GitHub](https://github.com/StevenMapes/django-aws-api-gateway-websockets) to start making changes.
- Clone the repository
- Initialise pre-commit by running ```pre-commit install```
- Install requirements from one of the requirement files depending on the versions of Python and Django you wish to use.
- Add a test case to show that the bug is fixed or the feature is implemented correctly.
- Test using ```python -W error::DeprecationWarning -W error::PendingDeprecationWarning -m coverage run --parallel -m pytest --ds tests.settings```
- Create a pull request, tagging the issue, bug me until I can merge your pull request. Also, don't forget to add yourself to AUTHORS.

# TO DO
1. Clean-up script for purging old sessions
2. Management command for triggering the clean-up.
3. Example of a "chat" implementation I.E. a view that receives a message and published the same message to all sessions 
within the same channel
4. Example of setting the channel within the default handler
5. Example of creating a custom route