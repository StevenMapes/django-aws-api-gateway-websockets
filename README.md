[![Read The Docs](https://img.shields.io/readthedocs/django-mysql?style=for-the-badge)](https://django-aws-api-gateway-websockets.readthedocs.io/)
![CI Build Status](https://img.shields.io/github/workflow/status/StevenMapes/django-aws-api-gateway-websockets/CI/main?style=for-the-badge)
![Coverage](https://img.shields.io/codecov/c/github/StevenMapes/django-aws-api-gateway-websockets/main?style=for-the-badge)

# Django AWS API Gateway Websockets
It is the aim of this project to create a uniform way to record websocket connections, associate the Django user who established the connection and then retrieve that user within each request.

This project is designed to work exclusively with AWS API Gateway.

It is not intended to be a replacement of [Django Channels](https://github.com/django/channels) instead this project allows you to add [WebSockets](https://en.wikipedia.org/wiki/WebSocket) support into your project by writing normal HTTP request-response views whilst allowing [AWS API Gateway](https://aws.amazon.com/api-gateway/) to worry about the WebSocket connection.

This project introduced a new [Class-Based-View](https://docs.djangoproject.com/en/dev/topics/class-based-views/) to handle connections, disconnections, routing, basic security checks and ensuring that the User object is available within every request.

The project will keep track of which users created which WebSockets, which ones are active and will allow you to send messages back down the socket to the client via Boto3.

Please refer to the installation notes and Getting Start Guides

# Python and Django Support
This project officially supports Python 3.8+ and Django 3.1+.

# Installation
## Django
You can install this package from pip using
```pip install django-aws-api-gateway-websockets```

### Updating settings.py
Add ```django_aws_api_gateway_websockets``` into ```INSTALLED_APPS``` 

Because the API Gateway will run from a subdomain you need to make sure your cookies are setup to allow subdomains.
Assuming your site runs from www.example.com and you wanted to use ws.www.example.com for websockets you would need to 
set the below
```
SESSION_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_DOMAIN='.www.example.com'
CSRF_COOKIE_DOMAIN='.www.example.com'
```

### URLS.py
Edit your urls.py file and add an entry for the URL you wish API Gateway to call. **IMPORTANT** The slug parameter 
must be called "route". This willbe populated by API Gateway with the route it uses E.G $connect, $default or 
$disconnect

E.G ```path("ws/<slug:route>", ExampleWebSocketView.as_view(), name="example_websocket")```

### SubClass the view
Subclass the WebSocketView and implement method where the name of the method is the name of the route AWS API Gateway
uses with the $ (dollar sign) remove.

You can then take whatever action you wish to take when a message is received by the server.


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


## AWS Setup
Create the new **Amazon API Gateway** as a WebSocket API...

### IAM Permissions
In order to publish messages to the API Gateway endpoint you will need to grant permissions to the IAM Role, or user, 
you wish to use.

I'm still reviewing the minimum required permissions but this project has been tested with the following being granted:

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
```"arn:aws:execute-api:REGION_NAME:YOUR_AWS_ACCOUNT_ID_HERE:*/*/*/*"``` where the REGION_NAME is the region you expect
or * and YOUR_AWS_ACCOUNT_ID_HERE is your account id

# Getting Started
TBA - This 

## Client Side Integration (Javascript)
This section will guide you through two common ways of connecting to and using this project from a webpage.

### Basic Integration
Below is a very basic integration using the WebSockets API built into browsers. It does not handle reconnecting dropped
websockets, see the next section for that.

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
let regDeskWSocket = new WebSocket(wss_url);
regDeskWSocket.onmessage = function(event) {
    // Take your action here to handle messages being received
    console.log(event);
    let msg = JSON.parse(event.data);
    console.log(msg);
};
```


### Reconnecting WebSockets
This example is using a 3rd party library

TBA

## Example of sending a message from the server to the client
The below example assumes that you are running an EC2 instance with an IAM role associated to that instance with the 
correct permissions. It also assumes you have set a varialbe within settings.py called AWS_REGION_NAME with the 
region your API Gateway API is in.

The connection ids will be stored within the model ```WebSocketSession```

```python
import boto3
import json
from django.conf import settings

api_id = "PUT-YOUR-API-GATEWAY-ID-HERE"
stage = "production"  # Change this to wahtever stage your API is at
region = settings.AWS_REGION_NAME

# This example assumes you wish to send the same mesaage to multiple connections
connection_ids = ["WebSocket-Connection-ID-1", "WebSocket-Connection-ID-2"]

# Build the payload to sent
data = json.dumps(dict(msg="This is a server sent message", message="would not be set"))

# Establish the connection
client = boto3.client(
    "apigatewaymanagementapi",
    endpoint_url=f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}",
    region_name=settings.AWS_REGION_NAME,
)

# Iterate and send
for connection_id in connection_ids:
    res = client.post_to_connection(Data=data, ConnectionId=connection_id)
```

If you are using anything other than a instance with an IAM role assigned then you'll need to pass the AWS Access Key and
AWS Secret Key within the boto3.client setup. E.G.
```
client = boto3.client(
    'apigatewaymanagementapi', 
    endpoint_url=f'https://{api_id}.execute-api.{region}.amazonaws.com/{stage}', 
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION_NAME
)
```

# Extending The View
TBA

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
