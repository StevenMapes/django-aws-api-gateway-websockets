from django.test import SimpleTestCase, override_settings

from django_aws_api_gateway_websockets import conf


class WebSocketsSettingSimpleTestCase(SimpleTestCase):
    def test_defaults(self):
        with override_settings(WEBSOCKETS={}):
            self.assertEqual(20, conf.get_setting("token_rate_limit_per_minute"))
            self.assertEqual(60, conf.get_setting("token_expiry_seconds"))
            self.assertEqual(20, conf.get_setting("rate_limit_max_attempts"))
            self.assertEqual(1, conf.get_setting("rate_limit_window_minutes"))

    def test_the_defaults_are_the_documented_ones(self):
        self.assertEqual(
            {
                "token_rate_limit_per_minute": 20,
                "token_expiry_seconds": 60,
                "rate_limit_max_attempts": 20,
                "rate_limit_window_minutes": 1,
            },
            conf.DEFAULTS,
        )

    @override_settings(WEBSOCKETS={"token_expiry_seconds": 15})
    def test_a_configured_value_wins_and_others_keep_their_defaults(self):
        self.assertEqual(15, conf.get_setting("token_expiry_seconds"))
        self.assertEqual(20, conf.get_setting("rate_limit_max_attempts"))

    def test_a_missing_or_unusable_dictionary_means_the_defaults(self):
        for value in (None, "nope", [], 5):
            with self.subTest(value=value):
                with override_settings(WEBSOCKETS=value):
                    self.assertEqual({}, conf.get_websockets_config())
                    self.assertEqual(60, conf.get_setting("token_expiry_seconds"))

    def test_a_missing_setting_means_the_defaults(self):
        with override_settings():
            from django.conf import settings

            del settings.WEBSOCKETS
            self.assertEqual(60, conf.get_setting("token_expiry_seconds"))

    def test_an_invalid_value_falls_back_to_the_default(self):
        """The system check reports it, so it is not silently accepted at start-up."""
        for bad in (0, -5, "30", None, 1.5, True, [30]):
            with self.subTest(value=bad):
                with override_settings(WEBSOCKETS={"token_expiry_seconds": bad}):
                    self.assertEqual(60, conf.get_setting("token_expiry_seconds"))

    def test_an_unknown_setting_name_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            conf.get_setting("no_such_setting")

    def test_known_keys_include_the_gateway_secret(self):
        self.assertIn("gateway_secret", conf.KNOWN_KEYS)
        self.assertLessEqual(set(conf.DEFAULTS), conf.KNOWN_KEYS)


class BooleanSettingSimpleTestCase(SimpleTestCase):
    def test_push_changes_to_aws_is_on_by_default(self):
        self.assertIs(True, conf.BOOLEAN_DEFAULTS["push_changes_to_aws"])
        with override_settings(WEBSOCKETS={}):
            self.assertIs(True, conf.get_boolean_setting("push_changes_to_aws"))

    def test_it_can_be_turned_off(self):
        with override_settings(WEBSOCKETS={"push_changes_to_aws": False}):
            self.assertIs(False, conf.get_boolean_setting("push_changes_to_aws"))

    def test_a_value_that_is_not_a_boolean_falls_back_to_the_default(self):
        for bad in (0, 1, "false", "no", None, [], 0.0):
            with self.subTest(value=bad):
                with override_settings(WEBSOCKETS={"push_changes_to_aws": bad}):
                    self.assertIs(True, conf.get_boolean_setting("push_changes_to_aws"))

    def test_an_unknown_name_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            conf.get_boolean_setting("token_expiry_seconds")

    def test_the_numeric_defaults_are_unchanged_by_the_new_key(self):
        self.assertNotIn("push_changes_to_aws", conf.DEFAULTS)
        self.assertIn("push_changes_to_aws", conf.KNOWN_KEYS)
