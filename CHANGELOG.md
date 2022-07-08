# 0.1.1 - 8th June 2022
- The channel set against the ```WebSocketSession``` is now determine by a new method.
The method looks at the QueryString first of all and if that it empty it then uses the default_channel_name set against
the ```APIGateway``` record that was found 
- Fixed a bug with _check_platform_registered_api_gateways to fix the NoneType issue
- Added the missing ```__str__``` method into the class as well as removing the imoprt that is no longer used
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


# 0.1.0 - 6th June 2022
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
