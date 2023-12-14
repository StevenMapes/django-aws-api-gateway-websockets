import json
from unittest.mock import MagicMock, call, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from django_aws_api_gateway_websockets.models import (
    ApiGateway,
    ApiGatewayAdditionalRoute,
    WebSocketSession,
    get_boto3_client,
)


class GetBoto3ClientTestCase(SimpleTestCase):
    @override_settings(
        AWS_IAM_PROFILE="FakeIAMProfile",
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_REGION_NAME=None,
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_exception_raised_if_no_credentials_other_than_aws_iam_profile(
        self, mock_boto3
    ):
        """Named profiles are not supported yet by this package. In theory they may be the preferred method for
         local and non-AWS hosted deployments.

         todo - I will add support in later

        :param MagicMock mock_boto3:
        :return:
        """
        with self.assertRaises(RuntimeError) as e:
            get_boto3_client("s3")

        self.assertEqual(
            str(e.exception), "AWS_REGION_NAME must be set within settings.py"
        )

    @override_settings(
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_REGION_NAME="eu-west-1",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_connection_made_if_aws_region_name_given_but_no_other_credentials(
        self, mock_boto3
    ):
        """This would be an example of the project running on an EC2 instance with a IAM profile assigned to it

        :param MagicMock mock_boto3:
        :return:
        """
        res = get_boto3_client("s3")
        mock_boto3.client.assert_called_with("s3", region_name="eu-west-1")

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_REGION_NAME="eu-west-1",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_additional_kwargs_are_passed_into_the_connection(self, mock_boto3):
        """Any additional kwargs passed into the function should be passed into the boto.client invocation

        :param MagicMock mock_boto3:
        :return:
        """
        res = get_boto3_client("s3", another="param")
        mock_boto3.client.assert_called_with(
            "s3", region_name="eu-west-1", another="param"
        )

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID="my-access-key",
        AWS_SECRET_ACCESS_KEY="my-secret-key",
        AWS_REGION_NAME="eu-west-1",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_access_key_and_secret_key_used(self, mock_boto3):
        """If the Access Key and Secret Key are defined within settings.py then they will be used. The region name
        must be also set

        :param MagicMock mock_boto3:
        :return:
        """
        res = get_boto3_client("s3")
        mock_boto3.client.assert_called_with(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME,
        )

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID="my-access-key",
        AWS_SECRET_ACCESS_KEY="my-secret-key",
        AWS_REGION_NAME="eu-west-1",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_service_defaults_to_apigatewayv2(self, mock_boto3):
        """If the service is not passed into the get_boto_client function then it should default to apigatewayv2

        :param MagicMock mock_boto3:
        :return:
        """
        res = get_boto3_client()
        mock_boto3.client.assert_called_with(
            "apigatewayv2",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME,
        )

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID="my-access-key",
        AWS_SECRET_ACCESS_KEY="my-secret-key",
        AWS_REGION_NAME="",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_region_name_is_required(self, mock_boto3):
        """If the Access Key and Secret Key are defined within settings.py  but the region is not set then an exception
        should be raised

        :param MagicMock mock_boto3:
        :return:
        """
        with self.assertRaises(RuntimeError) as e:
            get_boto3_client("s3")

        self.assertEqual(
            str(e.exception), "AWS_REGION_NAME must be set within settings.py"
        )


class ApiGatewaySimpleTestCase(SimpleTestCase):
    def test__str___returns_api_name(self):
        """The __str__ method should return the value of api_name"""
        self.assertEqual("My Api", str(ApiGateway(api_name="My Api")))

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_create_gateway__when_api_already_created(self, mocked_get_boto3_client):
        """Should return None without trying to create the API"""
        obj = ApiGateway(api_name="My Api", api_created=True)

        self.assertIsNone(obj.create_gateway())
        self.assertEqual(0, mocked_get_boto3_client.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "additional_routes")
    @patch.object(ApiGateway, "save")
    def test_create_gateway__no_errors(
        self,
        mocked_save,
        mocked_additional_routes,
        mocked__create_routes,
        mocked__create_stage_and_deploy,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        """When there are no errors the _create_api, _create_routes, _create_stage_and_deploy methods should be called"""
        obj = ApiGateway(pk=12, api_name="My Api", api_created=False)
        route_1 = ApiGatewayAdditionalRoute(deployed=True)
        route_2 = ApiGatewayAdditionalRoute(
            deployed=False, api_gateway=obj, integration_url="https://example.com/foo"
        )

        mocked_additional_routes.all.return_value = [route_1, route_2]
        obj = ApiGateway(pk=12, api_name="My Api", api_created=False)

        self.assertFalse(obj.api_created)
        obj.create_gateway()

        self.assertTrue(obj.api_created)
        mocked_get_boto3_client.assert_called_with()
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        mocked__create_routes.assert_called_with(mocked_get_boto3_client.return_value)
        mocked_additional_routes.all.assert_called_with()
        mocked_get_boto3_client.return_value.create_integration.assert_called_with(
            ApiId=route_2.api_gateway.api_id,
            ConnectionType="INTERNET",
            IntegrationMethod="POST",
            IntegrationType="HTTP_PROXY",
            IntegrationUri=route_2.integration_url,
            PassthroughBehavior="WHEN_NO_MATCH",
            PayloadFormatVersion="1.0",
            RequestParameters={
                "integration.request.header.connectionId": "context.connectionId"
            },
            TimeoutInMillis=29000,
        )
        mocked__create_stage_and_deploy.assert_called_with(
            mocked_get_boto3_client.return_value
        )
        mocked_save.assert_called_with()

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "save")
    def test_create_gateway__when_create_api_raises_error(
        self,
        mocked_save,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        """When an exception is called during create_api the other methods should not be called and the api_created
        property should be left as False
        """
        obj = ApiGateway(api_name="My Api", api_created=False)

        mocked___create_api.side_effect = Exception("Unexpected Error")

        with self.assertRaises(Exception) as e:
            self.assertFalse(obj.api_created)
            obj.create_gateway()

        self.assertEqual("Unexpected Error", str(e.exception))

        mocked_get_boto3_client.assert_called_with()
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        self.assertFalse(obj.api_created)
        self.assertEqual(0, mocked__create_routes.call_count)
        self.assertEqual(0, mocked__create_stage_and_deploy.call_count)
        self.assertEqual(0, mocked_save.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "save")
    def test_create_gateway__when__create_routes_raises_clienterror(
        self,
        mocked_save,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        """When an exception is called during _create_routes the other methods should not be called BUT the api_created
        property should be sert to as True
        """
        obj = ApiGateway(api_name="My Api", api_created=False)

        mocked__create_routes.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}}, "apigateway"
        )
        with self.assertRaises(Exception) as e:
            self.assertFalse(obj.api_created)
            obj.create_gateway()

        self.assertTrue(obj.api_created)
        mocked_save.assert_called_with()
        self.assertEqual(
            "An error occurred (ABC123) when calling the apigateway operation: Actual Error Here",
            str(e.exception),
        )

        mocked_get_boto3_client.assert_called_with()
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        mocked__create_routes.assert_called_with(mocked_get_boto3_client.return_value)
        self.assertEqual(0, mocked__create_stage_and_deploy.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "save")
    def test_create_gateway__when__create_stage_and_deploy_clienterror(
        self,
        mocked_save,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        """When an exception is called during _create_stage_and_deploy the api_created property should be set to as
        True
        """
        obj = ApiGateway(api_name="My Api", api_created=False)

        mocked__create_stage_and_deploy.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}}, "apigateway"
        )
        with self.assertRaises(Exception) as e:
            self.assertFalse(obj.api_created)
            obj.create_gateway()

        self.assertTrue(obj.api_created)
        mocked_save.assert_called_with()
        self.assertEqual(
            "An error occurred (ABC123) when calling the apigateway operation: Actual Error Here",
            str(e.exception),
        )

        mocked_get_boto3_client.assert_called_with()
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        mocked__create_routes.assert_called_with(mocked_get_boto3_client.return_value)
        mocked__create_stage_and_deploy.assert_called_with(
            mocked_get_boto3_client.return_value
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_domain_name")
    @patch.object(ApiGateway, "_create_api_mapping")
    @patch.object(ApiGateway, "save")
    def test_create_custom_domain__raises_valueerror_when_api_created_is_false(
        self,
        mocked_save,
        mocked__create_api_mapping,
        mocked__create_domain_name,
        mocked_get_boto3_client,
    ):
        """When api_created is False then a ValueError should be raised"""
        obj = ApiGateway(api_name="My Api", api_created=False)

        with self.assertRaises(Exception) as e:
            obj.create_custom_domain()

        self.assertEqual(
            str(e.exception), "The API needs to be created before calling this method"
        )

        self.assertEqual(0, mocked_get_boto3_client.call_count)
        self.assertEqual(0, mocked__create_domain_name.call_count)
        self.assertEqual(0, mocked__create_api_mapping.call_count)
        self.assertEqual(0, mocked_save.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_domain_name")
    @patch.object(ApiGateway, "_create_api_mapping")
    @patch.object(ApiGateway, "save")
    def test_create_custom_domain__raises_valueerror_when_certificate_arn_is_not_set(
        self,
        mocked_save,
        mocked__create_api_mapping,
        mocked__create_domain_name,
        mocked_get_boto3_client,
    ):
        """When api_created is True but the certificate_arn is not set then a ValueError should be raised"""
        obj = ApiGateway(api_name="My Api", api_created=True, certificate_arn="")

        with self.assertRaises(Exception) as e:
            obj.create_custom_domain()

        self.assertEqual(str(e.exception), "A Certificate ARN is required")

        self.assertEqual(0, mocked_get_boto3_client.call_count)
        self.assertEqual(0, mocked__create_domain_name.call_count)
        self.assertEqual(0, mocked__create_api_mapping.call_count)
        self.assertEqual(0, mocked_save.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_domain_name")
    @patch.object(ApiGateway, "_create_api_mapping")
    @patch.object(ApiGateway, "save")
    def test_create_custom_domain__as_expected(
        self,
        mocked_save,
        mocked__create_api_mapping,
        mocked__create_domain_name,
        mocked_get_boto3_client,
    ):
        """When api_created is False, the certificate arn is set and no errors are raised"""
        domain_result = {
            "DomainNameConfigurations": [
                {"ApiGatewayDomainName": "api-gateway.websocket.example.com"}
            ]
        }
        mocked__create_domain_name.return_value = domain_result

        obj = ApiGateway(
            api_name="My Api",
            api_created=True,
            certificate_arn="aws123:zxcv:3455",
            custom_domain_created=False,
            api_gateway_domain_name="",
            api_mapping_id="",
        )

        self.assertFalse(obj.custom_domain_created)

        obj.create_custom_domain()

        mocked_get_boto3_client.assert_called_with()
        mocked__create_domain_name.assert_called_with(
            mocked_get_boto3_client.return_value
        )
        mocked__create_api_mapping.asset_called_with(
            mocked_get_boto3_client.return_value
        )
        mocked_save.assert_called_with()

        self.assertTrue(obj.custom_domain_created)
        self.assertEqual(
            "api-gateway.websocket.example.com", obj.api_gateway_domain_name
        )
        self.assertEqual(obj.api_mapping_id, mocked__create_api_mapping.return_value)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_domain_name")
    @patch.object(ApiGateway, "_create_api_mapping")
    @patch.object(ApiGateway, "save")
    def test_create_custom_domain__clienterror_raised(
        self,
        mocked_save,
        mocked__create_api_mapping,
        mocked__create_domain_name,
        mocked_get_boto3_client,
    ):
        """When api_created is False, the certificate arn is set and no errors are raised"""
        mocked__create_api_mapping.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}}, "apigateway"
        )

        domain_result = {
            "DomainNameConfigurations": [
                {"ApiGatewayDomainName": "api-gateway.websocket.example.com"}
            ]
        }
        mocked__create_domain_name.return_value = domain_result

        obj = ApiGateway(
            api_name="My Api",
            api_created=True,
            certificate_arn="aws123:zxcv:3455",
            custom_domain_created=False,
            api_gateway_domain_name="",
            api_mapping_id="",
        )

        self.assertFalse(obj.custom_domain_created)

        with self.assertRaises(ClientError) as ce:
            obj.create_custom_domain()

        mocked_get_boto3_client.assert_called_with()
        mocked__create_domain_name.assert_called_with(
            mocked_get_boto3_client.return_value
        )
        mocked__create_api_mapping.asset_called_with(
            mocked_get_boto3_client.return_value
        )
        mocked_save.assert_called_with()

        self.assertTrue(obj.custom_domain_created)
        self.assertEqual(
            "api-gateway.websocket.example.com", obj.api_gateway_domain_name
        )
        self.assertEqual(
            str(ce.exception),
            "An error occurred (ABC123) when calling the apigateway operation: Actual Error Here",
        )

    def test__create_api(self):
        """When api_created is False, the certificate arn is set and no errors are raised"""
        client = MagicMock()
        client.create_api.return_value = {
            "ApiId": "1234ABCD",
            "ApiEndpoint": "https://api.amazon.com/this/url",
        }

        obj = ApiGateway(
            api_id="",
            api_endpoint="",
            api_key_selection_expression="$request.header.x-api-key",
            api_description="Some of description",
            api_name="",
            route_key="$default",
            route_selection_expression="$request.body.action",
            target_base_endpoint="https://example.com",
        )
        obj._create_api(client)

        client.create_api.assert_called_with(
            ApiKeySelectionExpression=obj.api_key_selection_expression,
            Description=obj.api_description,
            DisableSchemaValidation=True,
            Name=obj.api_name,
            ProtocolType="WEBSOCKET",
            RouteKey=obj.route_key,
            RouteSelectionExpression=obj.route_selection_expression,
            Target=f"{obj.target_base_endpoint}/default",
        )

        self.assertEqual("1234ABCD", obj.api_id)
        self.assertEqual("https://api.amazon.com/this/url", obj.api_endpoint)

    def test__create_routes(self):
        """create_integration and create_stage are should be called three times"""
        client = MagicMock()

        client.create_integration.side_effect = [
            {"IntegrationId": "i123-d345"},
            {"IntegrationId": "test-1234"},
            {"IntegrationId": "0997-tyty"},
        ]

        obj = ApiGateway(
            api_id="123456",
            api_endpoint="",
            api_key_selection_expression="$request.header.x-api-key",
            api_description="Some of description",
            api_name="",
            route_key="$default",
            route_selection_expression="$request.body.action",
            target_base_endpoint="https://example.com",
        )

        obj._create_routes(client)

        client.create_integration.assert_has_calls(
            [
                call(
                    ApiId=obj.api_id,
                    ConnectionType="INTERNET",
                    IntegrationMethod="POST",
                    IntegrationType="HTTP_PROXY",
                    IntegrationUri=f"{obj.target_base_endpoint}connect",
                    PassthroughBehavior="WHEN_NO_MATCH",
                    PayloadFormatVersion="1.0",
                    RequestParameters={
                        "integration.request.header.connectionId": "context.connectionId"
                    },
                    TimeoutInMillis=29000,
                ),
                call(
                    ApiId=obj.api_id,
                    ConnectionType="INTERNET",
                    IntegrationMethod="POST",
                    IntegrationType="HTTP_PROXY",
                    IntegrationUri=f"{obj.target_base_endpoint}disconnect",
                    PassthroughBehavior="WHEN_NO_MATCH",
                    PayloadFormatVersion="1.0",
                    RequestParameters={
                        "integration.request.header.connectionId": "context.connectionId"
                    },
                    TimeoutInMillis=29000,
                ),
                call(
                    ApiId=obj.api_id,
                    ConnectionType="INTERNET",
                    IntegrationMethod="POST",
                    IntegrationType="HTTP_PROXY",
                    IntegrationUri=f"{obj.target_base_endpoint}default",
                    PassthroughBehavior="WHEN_NO_MATCH",
                    PayloadFormatVersion="1.0",
                    RequestParameters={
                        "integration.request.header.connectionId": "context.connectionId"
                    },
                    TimeoutInMillis=29000,
                ),
            ]
        )

        client.create_route.assert_has_calls(
            [
                call(
                    ApiId=obj.api_id,
                    ApiKeyRequired=False,
                    AuthorizationType="NONE",
                    RouteKey="$connect",
                    Target=f"integrations/i123-d345",
                ),
                call(
                    ApiId=obj.api_id,
                    ApiKeyRequired=False,
                    AuthorizationType="NONE",
                    RouteKey="$disconnect",
                    Target=f"integrations/test-1234",
                ),
                call(
                    ApiId=obj.api_id,
                    ApiKeyRequired=False,
                    AuthorizationType="NONE",
                    RouteKey="$default",
                    Target=f"integrations/0997-tyty",
                    RouteResponseSelectionExpression="$default",
                ),
            ]
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test__create_stage_and_deploy(self, mocked_get_boto3_client):
        """Should return None without trying to create the API"""
        client = MagicMock()
        obj = ApiGateway(
            api_id="1234",
            api_name="My Api",
            stage_name="My Stage Name",
            stage_description="Some description",
        )
        obj._create_stage_and_deploy(client)

        client.create_stage.assert_called_with(
            ApiId=obj.api_id, StageName=obj.stage_name
        )
        client.create_deployment.assert_called_with(
            ApiId=obj.api_id,
            Description=obj.stage_description,
            StageName=obj.stage_name,
        )

    def test__create_domain_name__no_hosted_zone_id(self):
        """Test the parameters passed into the Boto3 client when the HostedZoneID is not set"""
        client = MagicMock()
        obj = ApiGateway(
            domain_name="example.com",
            certificate_arn="arn:aws:acm:region:account:certificate/certificate_ID",
            hosted_zone_id="",
        )
        obj._create_domain_name(client)

        client.create_domain_name.assert_called_with(
            DomainName=obj.domain_name,
            DomainNameConfigurations=[
                {
                    "CertificateArn": obj.certificate_arn,
                    "DomainNameStatus": "AVAILABLE",
                    "EndpointType": "REGIONAL",
                    "SecurityPolicy": "TLS_1_2",
                }
            ],
        )

    def test__create_domain_name__with_hosted_zone_id(self):
        """Test the parameters passed into the Boto3 client when the HostedZoneID is set"""
        client = MagicMock()
        obj = ApiGateway(
            domain_name="example.com",
            certificate_arn="arn:aws:acm:region:account:certificate/certificate_ID",
            hosted_zone_id="ABCD-123",
        )
        obj._create_domain_name(client)

        client.create_domain_name.assert_called_with(
            DomainName=obj.domain_name,
            DomainNameConfigurations=[
                {
                    "CertificateArn": obj.certificate_arn,
                    "DomainNameStatus": "AVAILABLE",
                    "EndpointType": "REGIONAL",
                    "SecurityPolicy": "TLS_1_2",
                    "HostedZoneId": obj.hosted_zone_id,
                }
            ],
        )

    def test__create_api_mapping(self):
        """Test the parameters passed into the Boto3 client when the HostedZoneID is set"""
        client = MagicMock()
        client.create_api_mapping.return_value = {"ApiMappingId": "MyID"}

        obj = ApiGateway(
            api_id=1234, domain_name="example.com", stage_name="development"
        )

        res = obj._create_api_mapping(client)

        client.create_api_mapping.assert_called_with(
            ApiId=obj.api_id, DomainName=obj.domain_name, Stage=obj.stage_name
        )
        self.assertEqual("MyID", res)


class ApiGatewayIntegrationTest(TestCase):
    def test_save_ensures_endpoint_ends_with_forward_slash(self):
        """The target_base_endpoint should also end with a trailing slash. If it is not set then it should be set by
        the save method
        """
        endpoints = [
            {
                "name": "test 1",
                "use": "http://www.example1.com/something",
                "result": "http://www.example1.com/something/",
            },
            {
                "name": "test 2",
                "use": "http://www.example1.com/something/",
                "result": "http://www.example1.com/something/",
            },
            {
                "name": "test 3",
                "use": "http://www.example1.com",
                "result": "http://www.example1.com/",
            },
            {
                "name": "test 4",
                "use": "http://www.example1.com/",
                "result": "http://www.example1.com/",
            },
        ]

        for config in endpoints:
            with self.subTest(config=config):
                api = ApiGateway(
                    api_name=config["name"],
                    api_description="A test api",
                    target_base_endpoint=config["use"],
                )
                api.save()
                self.assertEqual(
                    api.target_base_endpoint, config["result"], config["name"]
                )


class ApiGatewayAdditionalRouteSimpleTestCase(SimpleTestCase):
    def test__str__returns_name(self):
        """The __str__ of ApiGatewayAdditionalRoute should return the name attribute"""
        obj = ApiGatewayAdditionalRoute(name="My Test")
        self.assertEqual("My Test", str(obj))


class ApiGatewayAdditionalRouteIntegrationTestCase(TestCase):
    def setUp(self) -> None:
        self.non_deployed_api_gateway = ApiGateway(
            api_name="First Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            deployment_id="",
        )
        self.non_deployed_api_gateway.save()

        self.deployed_api_gateway = ApiGateway(
            api_name="Second Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example.com/ws/",
            deployment_id="ABC123",
        )
        self.deployed_api_gateway.save()

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_adding_route_to_gateway_with_no_deployment_id(
        self, mocked_get_boto3_client
    ):
        """When adding a route to a non-deployed gateway no post-save logic should run"""
        ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.non_deployed_api_gateway,
            name="Alternative Route",
            route_key="another-route",
            integration_url="https://www.example.com/ws/other",
            deployed=False,
        )
        self.assertEqual(0, mocked_get_boto3_client.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_adding_route_to_gateway_with_no_deployment_id_but_deployed_is_true(
        self, mocked_get_boto3_client
    ):
        """When adding a route to a non-deployed gateway no post-save logic should run even is deployed is True"""
        ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.non_deployed_api_gateway,
            name="Alternative Route",
            route_key="another-route",
            integration_url="https://www.example.com/ws/other",
            deployed=True,
        )
        self.assertEqual(0, mocked_get_boto3_client.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_adding_route_to_gateway_with_deployment_id_but_deployed_is_true(
        self, mocked_get_boto3_client
    ):
        """When saving an additional route where the deployed property is TRUE, the create_route method should not
        be called even as we expect the route has already been deployed another way
        """
        ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.deployed_api_gateway,
            name="Alternative Route",
            route_key="another-route",
            integration_url="https://www.example.com/ws/other",
            deployed=True,
        )
        self.assertEqual(0, mocked_get_boto3_client.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_adding_route_to_gateway_with_deployment_id_and_deployed_is_false(
        self, mocked_get_boto3_client
    ):
        """When saving an additional route where the deployed property is False and the API Gateway has a deployment ID
        then the new additional route should be automatically deployed
        """
        mocked_get_boto3_client.return_value.create_integration.return_value = {
            "IntegrationId": "Int-ID-123"
        }

        obj = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.deployed_api_gateway,
            name="Alternative Route",
            route_key="another-route",
            integration_url="https://www.example.com/ws/other",
            deployed=False,
        )

        self.assertTrue(obj.deployed)

        mocked_get_boto3_client.assert_called_with()
        mocked_get_boto3_client.return_value.create_integration.assert_called_with(
            ApiId=self.deployed_api_gateway.api_id,
            ConnectionType="INTERNET",
            IntegrationMethod="POST",
            IntegrationType="HTTP_PROXY",
            IntegrationUri=obj.integration_url,
            PassthroughBehavior="WHEN_NO_MATCH",
            PayloadFormatVersion="1.0",
            RequestParameters={
                "integration.request.header.connectionId": "context.connectionId"
            },
            TimeoutInMillis=29000,
        )
        mocked_get_boto3_client.return_value.create_route(
            ApiId=obj.api_gateway.api_id,
            ApiKeyRequired=False,
            AuthorizationType="NONE",
            RouteKey=obj.route_key,
            Target="integrations/Int-ID-123",
            RouteResponseSelectionExpression="$default",
        )
        mocked_get_boto3_client.return_value.create_deployment(
            ApiId=self.deployed_api_gateway.api_id,
            Description=self.deployed_api_gateway.stage_description,
            StageName=self.deployed_api_gateway.stage_name,
        )


class WebSocketSessionSimpleTestCase(SimpleTestCase):
    def test__str__returns_name(self):
        """The __str__ of WebSocketSession should return the connection_id attribute"""
        obj = WebSocketSession(connection_id="ABC-123")
        self.assertEqual("ABC-123", str(obj))


class WebSocketSessionIntegrationTestCase(TestCase):
    def setUp(self) -> None:
        self.api_gateway = ApiGateway.objects.create(
            api_name="First Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            deployment_id="",
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_REGION_NAME="eu-west-1")
    def test_send_message_return_response_on_success(self, mocked_get_boto3_client):
        """The return of post_to_connection should be returned on a positive send_message"""
        obj = WebSocketSession.objects.create(
            connection_id="ABC-123",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        data = {"action": "example", "msg": "Test Me"}

        res = obj.send_message(data)

        mocked_get_boto3_client.assert_called_with(
            "apigatewaymanagementapi",
            endpoint_url=(
                f"https://{obj.api_gateway.api_id}.execute-api."
                f"{settings.AWS_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
            ),
        )
        mocked_get_boto3_client.return_value.post_to_connection.assert_called_with(
            Data=json.dumps(data), ConnectionId=obj.connection_id
        )
        self.assertEqual(
            mocked_get_boto3_client.return_value.post_to_connection.return_value, res
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_REGION_NAME="eu-west-1")
    def test_send_message_boto3_gone_away(self, mocked_get_boto3_client):
        """When a GoneException is raised by Boto3 then an exception is not bubbled but the connected property is set
        to False
        """
        mocked_get_boto3_client.return_value.post_to_connection.side_effect = (
            ClientError(
                {"Error": {"Code": "GoneException", "Message": "Actual Error Here"}},
                "apigateway",
            )
        )

        obj = WebSocketSession.objects.create(
            connection_id="ABC-123",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        data = {"action": "example", "msg": "Test Me"}

        obj.send_message(data)

        mocked_get_boto3_client.assert_called_with(
            "apigatewaymanagementapi",
            endpoint_url=(
                f"https://{obj.api_gateway.api_id}.execute-api."
                f"{settings.AWS_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
            ),
        )
        mocked_get_boto3_client.return_value.post_to_connection.assert_called_with(
            Data=json.dumps(data), ConnectionId=obj.connection_id
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_REGION_NAME="eu-west-1")
    def test_send_message_raises_other_boto3_exceptions(self, mocked_get_boto3_client):
        """When a GoneException is raised by Boto3 then an exception is not bubbled but the connected property is set
        to False
        """
        mocked_get_boto3_client.return_value.post_to_connection.side_effect = (
            ClientError(
                {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}},
                "apigateway",
            )
        )

        obj = WebSocketSession.objects.create(
            connection_id="ABC-123",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        data = {"action": "example", "msg": "Test Me"}

        with self.assertRaises(ClientError):
            obj.send_message(data)

        mocked_get_boto3_client.assert_called_with(
            "apigatewaymanagementapi",
            endpoint_url=(
                f"https://{obj.api_gateway.api_id}.execute-api."
                f"{settings.AWS_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
            ),
        )


class WebSocketSessionQuerySetIntegrationTestCase(TestCase):
    # todo - Implement these tests
    pass
