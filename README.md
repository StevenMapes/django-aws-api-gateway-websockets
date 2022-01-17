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


# Installation
## Django
You can install this package from pip using
```pip install django-aws-api-gateway-websockets```

### Updating settings.py
Add ```django_aws_api_gateway_websockets``` into ```INSTALLED_APPS``` 

## AWS Setup
Create the new **Amazon API Gateway** as a WebSocket API...

# Getting Started
TBA - This 

## Client Side Integration (Javascript)
This section will guide you through two common ways of connecting to and using this project from a webpage.

### Basic Integration
TBA


### Reconnecting WebSockets
TBA

# Extending The View
TBA

# Found a Bug?
Issues are tracked via GitHub issues at the [project issue page](https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues)

# Have A Feature Request?
Feature requests can be raised by creating an issue within the [project issue page](https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues), but please create the issue with "Feature Request -" at the start of the issue

# Documentation
TBA

# Compiling Requirements
Run ```pip install pip-tools``` then run compile.py to generate the various requirements files
Also require ```pytest-django``` for testing

# Testing
# pip-tools
# tox

# Contributing
- [Check for open issues](https://github.com/StevenMapes/django-aws-api-gateway-websockets/issues) at the project issue page or open a new issue to start a discussion about a feature or bug.
- Fork the [repository on GitHub](https://github.com/StevenMapes/django-aws-api-gateway-websockets) to start making changes.
- Add a test case to show that the bug is fixed or the feature is implemented correctly.
- Create a pull request, tagging the issue, bug me until I can merge your pull request. Also, don't forget to add yourself to AUTHORS.
