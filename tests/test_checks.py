from unittest.mock import patch

from django.core import checks
from django.test import SimpleTestCase, override_settings
from django.urls import path

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


class UnlistedChannelsCheckSimpleTestCase(SimpleTestCase):
    def test_a_routed_view_that_allows_unlisted_channels_is_found(self):
        from tests import urls

        found = ws_checks._routed_views_allowing_unlisted_channels()

        self.assertEqual(
            [urls.ChatWebSocketView, urls.OpenChatWebSocketView],
            sorted(found, key=lambda view: view.__name__),
        )

    def test_a_warning_names_each_view_that_allows_unlisted_channels(self):
        result = ws_checks.check_unlisted_channels_are_refused(None)

        self.assertEqual(
            ["django_aws_api_gateway_websockets.W004"] * 2, [r.id for r in result]
        )
        self.assertIsInstance(result[0], checks.Warning)
        self.assertIn("ChatWebSocketView", result[0].msg)
        self.assertIn("OpenChatWebSocketView", result[1].msg)
        self.assertIn("ALLOW_UNLISTED_CHANNELS = False", result[0].hint)

    def test_no_warning_when_every_routed_view_refuses_unlisted_channels(self):
        with patch.object(
            ws_checks, "_routed_views_allowing_unlisted_channels", return_value=[]
        ):
            self.assertEqual([], ws_checks.check_unlisted_channels_are_refused(None))

    def test_a_view_that_refuses_unlisted_channels_is_not_reported(self):
        from tests import urls

        class Closed(urls.ChatWebSocketView):
            ALLOW_UNLISTED_CHANNELS = False

        patterns = [path("closed/<slug:route>", Closed.as_view())]
        with patch.object(ws_checks, "_url_patterns", return_value=patterns):
            self.assertEqual([], ws_checks._routed_views_allowing_unlisted_channels())

    def test_the_check_is_a_deploy_check(self):
        self.assertIn(
            ws_checks.check_unlisted_channels_are_refused,
            checks.registry.registry.get_checks(include_deployment_checks=True),
        )
        self.assertNotIn(
            ws_checks.check_unlisted_channels_are_refused,
            checks.registry.registry.get_checks(include_deployment_checks=False),
        )


class AllowedIntegrationHostsCheckSimpleTestCase(SimpleTestCase):
    def test_a_string_or_a_list_of_strings_is_accepted(self):
        for value in ("www.example.com", ["a.example.com", "*.example.com"], []):
            with self.subTest(value=value):
                with override_settings(WEBSOCKETS={"allowed_integration_hosts": value}):
                    self.assertEqual([], ws_checks.check_websockets_setting(None))

    def test_anything_else_is_an_error_that_does_not_show_the_value(self):
        for value in (5, True, {"a": "b"}, ["ok.example.com", 7], ["", "x"]):
            with self.subTest(value=value):
                with override_settings(WEBSOCKETS={"allowed_integration_hosts": value}):
                    result = ws_checks.check_websockets_setting(None)

                self.assertEqual(
                    ["django_aws_api_gateway_websockets.E002"], [r.id for r in result]
                )
                self.assertIn("allowed_integration_hosts", result[0].msg)


class ImplicitHandlersCheckSimpleTestCase(SimpleTestCase):
    def _view(self, **attrs):
        from django_aws_api_gateway_websockets.views import WebSocketView

        def chat(self, request, *args, **kwargs):
            return None

        methods = {"chat": chat}
        methods.update(attrs)
        return type("ChatView", (WebSocketView,), methods)

    def test_a_view_with_methods_and_no_explicit_list_is_reported(self):
        view = self._view()
        with patch.object(ws_checks, "_routed_view_classes", return_value=[view]):
            result = ws_checks.check_handlers_are_listed(None)

        self.assertEqual(
            ["django_aws_api_gateway_websockets.W005"], [r.id for r in result]
        )
        self.assertIsInstance(result[0], checks.Warning)
        self.assertIn("ChatView", result[0].msg)
        self.assertIn("ALLOWED_HANDLERS", result[0].hint)

    def test_a_view_with_an_explicit_list_is_not_reported(self):
        view = self._view(ALLOWED_HANDLERS={"chat"})
        with patch.object(ws_checks, "_routed_view_classes", return_value=[view]):
            self.assertEqual([], ws_checks.check_handlers_are_listed(None))

    def test_a_view_with_no_methods_of_its_own_is_not_reported(self):
        from django_aws_api_gateway_websockets.views import WebSocketView

        with patch.object(
            ws_checks, "_routed_view_classes", return_value=[WebSocketView]
        ):
            self.assertEqual([], ws_checks.check_handlers_are_listed(None))

    def test_a_view_that_only_overrides_hooks_is_not_reported(self):
        view = type(
            "HookView",
            (self._view().__mro__[1],),
            {"can_join_channel": lambda self, request, channel_name: True},
        )
        with patch.object(ws_checks, "_routed_view_classes", return_value=[view]):
            self.assertEqual([], ws_checks.check_handlers_are_listed(None))

    def test_the_routed_views_in_the_project_are_found(self):
        from tests import urls

        found = ws_checks._routed_view_classes()

        self.assertIn(urls.ChatWebSocketView, found)
        self.assertEqual(len(found), len(set(found)))

    def test_the_check_is_a_deploy_check(self):
        self.assertIn(
            ws_checks.check_handlers_are_listed,
            checks.registry.registry.get_checks(include_deployment_checks=True),
        )
        self.assertNotIn(
            ws_checks.check_handlers_are_listed,
            checks.registry.registry.get_checks(include_deployment_checks=False),
        )
