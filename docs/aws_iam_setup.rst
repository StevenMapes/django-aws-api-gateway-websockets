AWS IAM Setup
=============

Overview
--------

Django-AWS-API-Gateway-WebSockets interacts with AWS services to create,
configure, and use WebSocket API Gateway resources.

The exact permissions required depend on which features you use.

Common AWS services involved include:

* API Gateway V2;
* API Gateway Management API;
* ACM;
* Route 53;
* CloudWatch Logs, depending on your API Gateway logging configuration.

Recommended approach
--------------------

For production systems, use a dedicated IAM role or IAM user with the smallest
set of permissions required for your deployment.

Avoid using administrator credentials.

Separate deployment permissions from runtime permissions where possible.

Deployment permissions
----------------------

Deployment permissions are needed when your application or deployment process
creates or modifies AWS resources.

These may include permissions to:

* create and update WebSocket APIs;
* create routes and integrations;
* deploy API Gateway stages;
* configure custom domains;
* read ACM certificates;
* create or update Route 53 records.

Runtime permissions
-------------------

Runtime permissions are needed when Django sends messages to active WebSocket
connections.

These usually include permission to call the API Gateway Management API action
used to post messages back to connected clients.

Example policy structure
------------------------

I'm still reviewing the minimum required permissions, but this project has been
tested with the following IAM policy.

You can copy and paste it into the JSON editor within the AWS console and then
replace the following placeholders:

``{AWS-REGION-NAME}``
   The AWS region you are using, for example ``eu-west-1``. If you want to grant
   access to all regions, replace this placeholder with ``*``.

``{AWS-ACCOUNT-NUMBER}``
   Your AWS account number, for example ``123456789101``.

.. code-block:: json

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

Hardening the policy
--------------------

Before using the policy in production, you may wish to:

* replace wildcard resources with specific ARNs where possible;
* separate deployment permissions from runtime permissions;
* restrict Route 53 permissions to the required hosted zone;
* restrict API Gateway permissions to the required APIs;
* rotate credentials regularly if using IAM users;
* prefer IAM roles for AWS-hosted runtime environments.