# 1.4.0 - 8th June 2025
- Introduce two Django CBV mixins to speed up development for projects using this library.
- ```AddWebSocketRouteToContextMixin``` this mixin can vbe added to CBV views that need to connect to and send message
to the server via Websockets. It allows you to specific the ```route_key``` to use to idnetify the WebSocket route you
created (defaulting to the "default" route), as well as adding a class property and context key of "channel_name" that
can be used within the HTML templates to connect to the channel intended to be used by the view.
- ```AppChannelWebSocketMixin``` this mixin extends the first with the intention of being used by CBVs where the both
the ```route_key``` and ```channel_name``` are the same and *BOTH* are the same names as the app. This is useful in the
design paradigm where you are going to have one WebSocket endpoint per app handling the server-side requests. This way
you can create the route key to match the Django app name and then use this mixin to extend the CBVs that render the
client facing HTML.

For example if you have the app *blog* with the following CBV defined within the views.py

```
class IndexView(AppChannelWebSocketMixin, TemplateView):
    template_name = "blog/index.htm"
```
Then you create an ```ApiGatewayAdditionalRoute``` entry with a ```route_key``` of **blog** so that the you can then
create a Django template such as the below which can be included on any page on your project that requires websocket
connectivity to define the connection

```html
<script src="js/reconnecting-websocket.min.js"" crossorigin="anonymous"></script>
{% with api_gateway_route.api_gateway as websocket %}
<script
    data-wss-url="wss://{{ websocket.domain_name }}"
    data-ws-channel="{{ channel_name }}"
    data-ws-route-key="{{ api_gateway_route.route_key }}"
>
{% endwith %}
let window.scWebSocketConnected = false;
let scriptData = document.currentScript.dataset;
let pageWebSocket = new ReconnectingWebSocket(
    `${scriptData.wssUrl}?channel=${scriptData.wsChannel}`, null, {debug:false, reconnectInterval:3000}
);
```

Full examples of how to use this project with re-usable JS for the client and CBVs for the server will be published
soon.

# 1.3.0 - 26th May 2025
- Added in support for AWS Profiles
- Updated the documentation to include examples of how to configure settings.py

# 1.2.1 - 12th May 2025
- 1.2.0 was built using an older version so the package had the wrong name, it's been yanked, so use 1.2.1 instead

# 1.2.0 - 12th May 2025 - yanked
- Dropped support for Django 5.0
- This package should still work with those combinations but they are no longer being tested

# 1.1.3 - 7th May 2025
- Updated pyproject.toml to show Django 5.2 support, also updated the pre-commit-config and requirements or testings 

# 1.1.2 - 17th March 2025
- Removed Python 3.8 support

# 1.1.1 - 20th November 2024
- Updated the tox tests to include support for Django 5.2a.1 with Python 3.10, 3.11, 3.12, 3.13 and 3.14 
 
# 1.1.0 - 19th November 2024
- Fixes possible security issue #17 to remove the direct use of headers being passed into the Bad Request Response.
- Changed the response send by the bad request response
- Updating requirements

# 1.0.22 - 21st October 2024
- Updated github actions to collect and display coverage reports
- Updated tox to include tests for Python 3.13 with Django 4.2, 5.0 and 5.1
- Updated tox to include tests for Python 3.14.0-alpha1 with Django 5.1
- Updated main.yml to use [UV](https:/yes/github.com/astral-sh/uv) for faster testing

# 1.0.21 - 4th August 2024
- Includes the PR for .github/workflows/main.yml as well as updating to show support for Django 5.1

# 1.0.20 - 15th July 2024
- Dependency update for security fix 

# 1.0.19 - 11th July 2024
- Updating the requirements for the pipline to use Django 5.0.7 or Django 4.2.14
 
- # 1.0.18 - 2nd July 2024
- Updating the requirements so Python 3.10+ requires urllib3>=2.2.2 due to the security issues with 2.0.0 through 2.2.1

# 1.0.17 - 28th May 2024
- Bumping required sqlparse version for Django 4.2 and 5.0 to be 0.5.0 due to security fix for DOS in sqlparse<5.0.0 
within the requirements files used for testing.
 
# 1.0.16 - 24th May 2024
- Added in test for Django 5.1a1

# 1.0.15 - 7th May 2024
- Upgrade black, blacken-docs and isort within precommit, removed black from the requirements as it's only used by
pre-commit

# 1.0.14 - 7th May 2024
- Removing support for Django < 4.2.0. This project will probably still work with Django 3.2+ but I'm now longer going
to support it with tests.
- Bumped requirements as well

# 1.0.13 - 14th December 2023
- Adding Django 4.2 into the matrix of tests replacing 4.2a1
- Adding Django 5 into the tox runner

# 1.0.12 - 20th September 2023
- Updating the README file with additional examples.
- Adding in additional unit tests to improve coverage from 86% to 96%.
- Adding Django 4.2 into the matrix of tests replacing 4.2a1
- Adding Django 5 into the tox runner

# 1.0.11 - 18th January 2023
- Adding Django 4.2a1 into the matrix of tests

# 1.0.10 - 15th December 2022
- Fixing an issue where ```ApiGatewayAdditionalRoute``` had a unique constraint on the ```route_key``` when it should 
have been a composite unique constraint on the  ```api_gateway``` and the ```route_key``` 

# 1.0.9 - 12th December 2022
- Fixing an issue within the dispatch method of the view where the route key was missing from the arg. Now continues 
with the checks. 

# 1.0.8 - 9th December 2022
- Corrected the examples of the CSRF and Session values on the README file.

# 1.0.7 - 9th December 2022
- Added in tests for Python 3.11
- Removed use of CodeCov and moved to use GitHUb actions to store and report on the coverage.
- Actions fail if coverage drops below 85%, this threshold will be increased in the future as I add in additional tests
- Updated requirements and removed legacy tox files
- Updated version of gitHub Actions
- Added link to the PyPi site from the readme

# 1.0.6 - 9th December 2022
- Updating the listing pages to include whether the additional route has been deployed or not
- Updated the README file

# 1.0.0 - 1.0.5 - 8th December 2022
- Added support for additional custom routes for each API. This means that you could use one API Gateway for an entire
project if you wished to using the ```ApiGatewayAdditionalRoute``` to route requests to different URLs within your 
project.  This is extremely useful if you have multiple apps that require websockets. The recommendation is to have a 
central view that handles all connections, disconnections and the default route. Then to use specific route for each of
your apps, views or however you require to separate requests.

# 0.2.2 - 20th September 2022
- Added in additional unit tests. Still requires additional tests for full coverage

# 0.2.1 - 13th September 2022
- BUG FIX - The ```_create_domain_name``` method of the ```ApiGateway``` was always setting a hosted zone id even if one
was not to be used.
- Updating the README.md file with the updated IAM policy

# 0.2.0 - 12th September 2022
- Updating the packaging of the project as the management command was not being bundled with the rest of the code.

# 0.1.5 - 4th August 2022
- Adding in a supplementary list of headers that are also required, by default, but that you may need to blank out when
testing from a non-AWS deployment such as via na ngrok proxy
- Adding the management command to stale connections 

# 0.1.4 - 4th August 2022
- Correcting the name on the license
- Updating the README setup instructions including the required Django settings
- Adding Exception handling into the Django Admin page so that the exceptions are caught and added to Django messages
- Ensures the trailing / is appended to the target base endpoint.

# 0.1.3 - 4th August 2022
- License is now MIT
- Now considered as in Beta
- Supports Django 3.2, 4.0 and 4.1
- Supports Python 3.8 through 3.10

# 0.1.2 - 29th June 2022
- Updated the dispatch method of WebSocketView to add in the default positive response if the handling method that was
called does not return a response. This means that unless you are returning a negative response the handling methods no
longer need to return anything.
- Updated the README with examples of writing individual methods to handle different types of requests where the type
of request is determined by the value of the ```route_selection_key```.
- Updated the README with examples of how to send a reply to the websocket that made the request as well as how to send
a Multicast to all connections using the same "channel".
- 
# 0.1.1 - 25th June 2022
- Added debugging list to the base ```WebSocketView``` to keep track of calls if debugging is turned on. The intention
is that debug=True can be passed into the ```.as_view()``` method in order to debug issues. Then the dispatch method can
be overloaded to log the error to the logger the user wishes to use.
- Fixed a bug with the custom QuerySet so that if a ```GoneException``` is raised by boto3 then the websocket session
entry is updated to be flagged as no longer connected

# 0.1.0 - 8th June 2022
- The channel set against the ```WebSocketSession``` is now determine by a new method.
The method looks at the QueryString first of all and if that it empty it then uses the default_channel_name set against
the ```APIGateway``` record that was found 
- Fixed a bug with _check_platform_registered_api_gateways to fix the NoneType issue
- Added the missing ```__str__``` method into the class as well as removing the import that is no longer used
- Added the missing ```self.custom_domain_created = True``` into the ```create_custom_domain``` method
- Fixed a bug where formatting had converted the hosted zone id into a tuple 
- Fixed a bug around the boto3 client setup as the checks for the AWS_ACCESS_KEY were not tight enough so I've swapped 
the order 
- Fixed a bug where method name was typed wrong
- Fixed a bug where the wrong admin view had the custom actions
- Added new property to the base View called ```websocket_session``` which stores the websocket session for the request
for all non connect or disconnect requests 
- Added ```send_message``` method to the WebSocketSession class in order to send a message to the connection
- Added a new custom queryset class called ```WebSocketSessionQuerySet``` that implements a method to send a message
to every object within the current filter whilst ensuring it only sends to connections that are active
- Added the model ```ApiGateway```
- Updated ```WebSocketView``` to include validation of the ```aws_api_gateway_id``` property to allow views to be
created that only allow specific API Gateway endpoints to call them.
- Updated ```WebSocketView``` to include validation of the calling API Gateway endpoint to check that it's one of the
APIGateway records registered with the platform. **Note: Could do with updating to check a cache first**
- ```WebSocketSession``` now stores an FK to ```ApiGateway``` and is populated by the WebSocketView within the 
connection method
- The API Gateway ID within the header is now always checked against the database to help block unexpected sources. 
- Added two custom Django Admin functions ```create_api_gateway``` and ```create_custom_domain``` that can be used to
create the actual AWS API Gateway endpoint and custom domain.
- Added two management commands ```createApiGateway``` and ```createCustomDomain``` both of which take one parameter
which is the PK of the ApiGateway record you wish to run. These management commands run the same methods the admin
functions added above. They have been created to allow this package to be used without Django Admin but to still be 
able to automatically set-up API Gateway
- Created the initial logic to create the API Gateway and the Custom Domain as methods of the ApiGateway model. The 
intended use is to call ```obj.create_create_gateway()``` first then to call ```obj.create_custom_domain()``` once 
the SSL certificate is ready. These methods will update the record with the details required to update Route53 

# 0.0.1 - 17th Jan 2022
- Initial build with the base view and base model.
- Dropped support for Django < 3.1 due to use of PositiveBigInt and also drop support of Python < 3.8 
