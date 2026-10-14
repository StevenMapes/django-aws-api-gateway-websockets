from django.core import checks
from django.test import SimpleTestCase, override_settings

from django_aws_api_gateway_websockets import checks as ws_checks

GOOD = "s3cr3t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


class GatewaySecretChecksSimpleTestCase(SimpleTestCase):
    def test_no_error_when_no_secret_is_set(self):
        with override_settings(WEBSOCKETS=None):
            self.assertEqual([], ws_checks.check_gateway_secret_format(None))

    @override_settings(WEBSOCKETS={"gateway_secret": GOOD})
    def test_no_error_for_a_valid_secret(self):
        self.assertEqual([], ws_checks.check_gateway_secret_format(None))

    @override_settings(WEBSOCKETS={"gateway_secret": [GOOD, "0ld-" + "y" * 40]})
    def test_no_error_for_a_list_of_valid_secrets(self):
        self.assertEqual([], ws_checks.check_gateway_secret_format(None))

    def test_an_invalid_secret_is_an_error(self):
        for bad in ("short", "has'quote" + "x" * 40, "has space" + "x" * 40):
            with self.subTest(secret=bad):
                with override_settings(WEBSOCKETS={"gateway_secret": bad}):
                    result = ws_checks.check_gateway_secret_format(None)

                self.assertEqual(1, len(result))
                self.assertIsInstance(result[0], checks.Error)
                self.assertEqual("django_aws_api_gateway_websockets.E001", result[0].id)
                self.assertNotIn(bad, result[0].msg)

    def test_a_secret_with_a_trailing_newline_is_an_error_that_says_so(self):
        for bad in (GOOD + "\n", GOOD + "\r\n"):
            with self.subTest(secret=bad):
                with override_settings(WEBSOCKETS={"gateway_secret": bad}):
                    result = ws_checks.check_gateway_secret_format(None)

                self.assertEqual(
                    ["django_aws_api_gateway_websockets.E001"], [r.id for r in result]
                )
                self.assertIn("newline", result[0].hint)

    def test_a_non_string_secret_is_an_error(self):
        with override_settings(WEBSOCKETS={"gateway_secret": 12345}):
            result = ws_checks.check_gateway_secret_format(None)

        self.assertEqual(
            ["django_aws_api_gateway_websockets.E001"], [r.id for r in result]
        )

    def test_deploy_warning_when_no_secret_is_set(self):
        for websockets in (None, {}, {"gateway_secret": ""}):
            with self.subTest(websockets=websockets):
                with override_settings(WEBSOCKETS=websockets):
                    result = ws_checks.check_gateway_secret_is_set(None)

                self.assertEqual(1, len(result))
                self.assertIsInstance(result[0], checks.Warning)
                self.assertEqual("django_aws_api_gateway_websockets.W001", result[0].id)

    @override_settings(WEBSOCKETS={"gateway_secret": GOOD})
    def test_no_deploy_warning_when_a_secret_is_set(self):
        self.assertEqual([], ws_checks.check_gateway_secret_is_set(None))

    def test_the_checks_are_registered(self):
        registered = checks.registry.registry.get_checks(include_deployment_checks=True)

        self.assertIn(ws_checks.check_gateway_secret_format, registered)
        self.assertIn(ws_checks.check_gateway_secret_is_set, registered)
        self.assertNotIn(
            ws_checks.check_gateway_secret_is_set,
            checks.registry.registry.get_checks(include_deployment_checks=False),
        )


class WebSocketsSettingChecksSimpleTestCase(SimpleTestCase):
    def test_no_messages_when_nothing_is_set(self):
        for websockets in (None, {}):
            with self.subTest(websockets=websockets):
                with override_settings(WEBSOCKETS=websockets):
                    self.assertEqual([], ws_checks.check_websockets_setting(None))

    @override_settings(
        WEBSOCKETS={
            "token_rate_limit_per_minute": 10,
            "token_expiry_seconds": 30,
            "rate_limit_max_attempts": 5,
            "rate_limit_window_minutes": 2,
            "gateway_secret": GOOD,
        }
    )
    def test_no_messages_for_valid_settings(self):
        self.assertEqual([], ws_checks.check_websockets_setting(None))

    def test_a_value_that_is_not_a_positive_integer_is_an_error(self):
        for bad in (0, -1, "30", 1.5, None, True):
            with self.subTest(value=bad):
                with override_settings(WEBSOCKETS={"token_expiry_seconds": bad}):
                    result = ws_checks.check_websockets_setting(None)

                self.assertEqual(
                    ["django_aws_api_gateway_websockets.E002"], [r.id for r in result]
                )
                self.assertIsInstance(result[0], checks.Error)
                self.assertIn("token_expiry_seconds", result[0].msg)

    def test_push_changes_to_aws_must_be_true_or_false(self):
        for bad in (0, 1, "false", "no", None, []):
            with self.subTest(value=bad):
                with override_settings(WEBSOCKETS={"push_changes_to_aws": bad}):
                    result = ws_checks.check_websockets_setting(None)

                self.assertEqual(
                    ["django_aws_api_gateway_websockets.E002"], [r.id for r in result]
                )
                self.assertIsInstance(result[0], checks.Error)
                self.assertIn("push_changes_to_aws", result[0].msg)
                self.assertIn("True or False", result[0].msg)

    def test_push_changes_to_aws_true_and_false_are_valid(self):
        for good in (True, False):
            with self.subTest(value=good):
                with override_settings(WEBSOCKETS={"push_changes_to_aws": good}):
                    self.assertEqual([], ws_checks.check_websockets_setting(None))

    def test_a_dictionary_is_required(self):
        for bad in ("nope", ["a"], 5):
            with self.subTest(value=bad):
                with override_settings(WEBSOCKETS=bad):
                    result = ws_checks.check_websockets_setting(None)

                self.assertEqual(
                    ["django_aws_api_gateway_websockets.E002"], [r.id for r in result]
                )

    def test_an_unknown_key_is_a_warning_that_names_the_key_not_the_value(self):
        with override_settings(
            WEBSOCKETS={"token_expiry_second": 30, "token_expiry_seconds": 30}
        ):
            result = ws_checks.check_websockets_setting(None)

        self.assertEqual(
            ["django_aws_api_gateway_websockets.W002"], [r.id for r in result]
        )
        self.assertIsInstance(result[0], checks.Warning)
        self.assertIn("token_expiry_second", result[0].msg)

    def test_the_gateway_secret_key_is_not_reported_as_unknown(self):
        with override_settings(WEBSOCKETS={"gateway_secret": GOOD}):
            self.assertEqual([], ws_checks.check_websockets_setting(None))

    def test_region_warning_under_deploy_when_no_region_is_set(self):
        with override_settings(AWS_GATEWAY_REGION_NAME="", AWS_REGION_NAME=""):
            result = ws_checks.check_aws_region_is_set(None)

        self.assertEqual(
            ["django_aws_api_gateway_websockets.W003"], [r.id for r in result]
        )

    def test_no_region_warning_when_either_setting_is_set(self):
        for kwargs in (
            {"AWS_GATEWAY_REGION_NAME": "eu-west-1", "AWS_REGION_NAME": ""},
            {"AWS_GATEWAY_REGION_NAME": "", "AWS_REGION_NAME": "eu-west-1"},
        ):
            with self.subTest(**kwargs):
                with override_settings(**kwargs):
                    self.assertEqual([], ws_checks.check_aws_region_is_set(None))

    def test_the_new_checks_are_registered(self):
        registered = checks.registry.registry.get_checks(include_deployment_checks=True)
        not_deploy = checks.registry.registry.get_checks(
            include_deployment_checks=False
        )

        self.assertIn(ws_checks.check_websockets_setting, not_deploy)
        self.assertIn(ws_checks.check_aws_region_is_set, registered)
        self.assertNotIn(ws_checks.check_aws_region_is_set, not_deploy)
