from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from django_aws_api_gateway_websockets.models import ApiGateway, get_boto3_client


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
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "save")
    def test_create_gateway__no_errors(
        self,
        mocked_save,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        """When there are no errors the _create_api, _create_routes, _create_stage_and_deploy methods should be called"""
        obj = ApiGateway(api_name="My Api", api_created=False)

        self.assertFalse(obj.api_created)
        obj.create_gateway()

        self.assertTrue(obj.api_created)
        mocked_get_boto3_client.assert_called_with()
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        mocked__create_routes.assert_called_with(mocked_get_boto3_client.return_value)
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
