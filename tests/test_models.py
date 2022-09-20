from unittest.mock import MagicMock, patch

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
