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

The following is an intentionally broad example. You should restrict resources
and actions for your own AWS account and deployment.

.. code-block:: json

   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "apigateway:*"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "execute-api:ManageConnections"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "acm:DescribeCertificate",
           "acm:ListCertificates"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "route53:ChangeResourceRecordSets",
           "route53:GetHostedZone",
           "route53:ListHostedZones",
           "route53:ListResourceRecordSets"
         ],
         "Resource": "*"
       }
     ]
   }

Hardening the policy
--------------------

Before using the policy in production:

* replace wildcard resources with specific ARNs where possible;
* separate deployment permissions from runtime permissions;
* restrict Route 53 permissions to the required hosted zone;
* restrict API Gateway permissions to the required APIs;
* rotate credentials regularly if using IAM users;
* prefer IAM roles for AWS-hosted runtime environments.