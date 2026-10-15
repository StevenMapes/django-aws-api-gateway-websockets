import json
import threading
from unittest.mock import ANY, MagicMock, call, patch

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.db.models.signals import post_delete
from django.test import (
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from django_aws_api_gateway_websockets.models import (
    BROADCAST_CONNECT_TIMEOUT,
    BROADCAST_READ_TIMEOUT,
    GATEWAY_SECRET_HEADER,
    ApiGateway,
    ApiGatewayAdditionalRoute,
    ChannelPermission,
    ChannelPermissionRule,
    ConnectionRateLimit,
    WebSocketSession,
    WebSocketToken,
    _post_to_connection,
    clear_boto3_client_cache,
    collect_deferred_sync_errors,
    get_boto3_client,
    get_gateway_secrets,
    hash_session_key,
    integration_request_parameters,
    serialise_message,
)
from django_aws_api_gateway_websockets.sync import ApiGatewaySyncError

ALLOWED_HOSTS_SETTING = {
    "allowed_integration_hosts": ["www.example.com", "*.apps.example.com"]
}


class WebSocketTokenIntegrationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="token-user", password="password")

    def test_generate_token_creates_valid_token(self):
        token = WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key",
        )

        self.assertEqual(64, len(token.token))
        self.assertEqual(self.user, token.user)
        self.assertEqual(hash_session_key("session-key"), token.session_key)
        self.assertFalse(token.used)

    def test_generate_token_does_not_store_the_raw_session_key(self):
        token = WebSocketToken.generate_token(user=self.user, session_key="session-key")

        token.refresh_from_db()
        self.assertNotIn("session-key", token.session_key)
        self.assertEqual(64, len(token.session_key))

    def test_stored_hash_cannot_be_used_in_place_of_the_session_key(self):
        """Reading the column (admin, backup, SQL) must not be enough to spend a token"""
        token = WebSocketToken.generate_token(user=self.user, session_key="session-key")

        result = WebSocketToken.validate_and_consume(
            token.token, token.session_key, max_age_seconds=60
        )

        self.assertIsNone(result)

    def test_session_key_column_fits_the_hash(self):
        column = WebSocketToken._meta.get_field("session_key")

        self.assertGreaterEqual(column.max_length, len(hash_session_key("x")))

    def test_validate_and_consume_returns_user_and_marks_token_used(self):
        token = WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key",
        )

        result = WebSocketToken.validate_and_consume(
            token.token,
            "session-key",
            max_age_seconds=60,
        )

        token.refresh_from_db()
        self.assertEqual(self.user, result)
        self.assertTrue(token.used)

    def test_validate_and_consume_returns_none_for_invalid_token(self):
        result = WebSocketToken.validate_and_consume(
            "0" * 64,
            "session-key",
            max_age_seconds=60,
        )

        self.assertIsNone(result)

    def test_validate_and_consume_returns_none_for_wrong_session_key(self):
        token = WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key",
        )

        result = WebSocketToken.validate_and_consume(
            token.token,
            "other-session-key",
            max_age_seconds=60,
        )

        self.assertIsNone(result)

    def test_validate_and_consume_returns_none_for_used_token(self):
        token = WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key",
        )
        token.used = True
        token.save(update_fields=["used"])

        result = WebSocketToken.validate_and_consume(
            token.token,
            "session-key",
            max_age_seconds=60,
        )

        self.assertIsNone(result)

    def test_cleanup_expired_deletes_old_tokens(self):
        token = WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key",
        )
        WebSocketToken.objects.filter(pk=token.pk).update(
            created_at=timezone.now() - timezone.timedelta(seconds=301),
        )

        deleted_count, _ = WebSocketToken.cleanup_expired(max_age_seconds=300)

        self.assertEqual(1, deleted_count)
        self.assertFalse(WebSocketToken.objects.filter(pk=token.pk).exists())

    def test_check_rate_limit_returns_true_below_limit(self):
        WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key",
        )

        self.assertTrue(
            WebSocketToken.check_rate_limit(
                self.user,
                max_tokens_per_minute=2,
            )
        )

    def test_check_rate_limit_returns_false_at_limit(self):
        WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key-1",
        )
        WebSocketToken.generate_token(
            user=self.user,
            session_key="session-key-2",
        )

        self.assertFalse(
            WebSocketToken.check_rate_limit(
                self.user,
                max_tokens_per_minute=2,
            )
        )


class ConnectionRateLimitIntegrationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rate-user", password="password")

    def test_record_attempt_stores_authenticated_user(self):
        attempt = ConnectionRateLimit.record_attempt(
            ip_address="127.0.0.1",
            user=self.user,
            successful=True,
        )

        self.assertEqual("127.0.0.1", attempt.ip_address)
        self.assertEqual(self.user, attempt.user)
        self.assertTrue(attempt.successful)

    def test_record_attempt_ignores_anonymous_user(self):
        attempt = ConnectionRateLimit.record_attempt(
            ip_address="127.0.0.1",
            user=AnonymousUser(),
            successful=False,
        )

        self.assertIsNone(attempt.user)
        self.assertFalse(attempt.successful)

    def test_check_rate_limit_allows_when_under_limit(self):
        ConnectionRateLimit.record_attempt(
            ip_address="127.0.0.1",
            user=self.user,
            successful=False,
        )

        allowed, attempts = ConnectionRateLimit.check_rate_limit(
            ip_address="127.0.0.1",
            user=self.user,
            max_attempts=2,
            window_minutes=5,
        )

        self.assertTrue(allowed)
        self.assertEqual(1, attempts)

    def test_check_rate_limit_blocks_by_ip(self):
        ConnectionRateLimit.record_attempt(
            ip_address="127.0.0.1",
            user=None,
            successful=False,
        )

        allowed, attempts = ConnectionRateLimit.check_rate_limit(
            ip_address="127.0.0.1",
            max_attempts=1,
            window_minutes=5,
        )

        self.assertFalse(allowed)
        self.assertEqual(1, attempts)

    def test_check_rate_limit_blocks_by_user(self):
        ConnectionRateLimit.record_attempt(
            ip_address="127.0.0.1",
            user=self.user,
            successful=False,
        )

        allowed, attempts = ConnectionRateLimit.check_rate_limit(
            ip_address="127.0.0.2",
            user=self.user,
            max_attempts=1,
            window_minutes=5,
        )

        self.assertFalse(allowed)
        self.assertEqual(1, attempts)

    def test_cleanup_old_records_deletes_old_attempts(self):
        attempt = ConnectionRateLimit.record_attempt(
            ip_address="127.0.0.1",
            user=self.user,
            successful=False,
        )
        ConnectionRateLimit.objects.filter(pk=attempt.pk).update(
            attempt_time=timezone.now() - timezone.timedelta(days=8),
        )

        deleted_count, _ = ConnectionRateLimit.cleanup_old_records(days=7)

        self.assertEqual(1, deleted_count)
        self.assertFalse(ConnectionRateLimit.objects.filter(pk=attempt.pk).exists())

    def test_the_check_is_one_query_for_a_user_and_for_an_anonymous_client(self):
        with self.assertNumQueries(1):
            ConnectionRateLimit.check_rate_limit("127.0.0.1", self.user)
        with self.assertNumQueries(1):
            ConnectionRateLimit.check_rate_limit("127.0.0.1", AnonymousUser())
        with self.assertNumQueries(1):
            ConnectionRateLimit.check_rate_limit("127.0.0.1")

    def test_the_check_counts_the_ip_and_the_user_separately(self):
        other = User.objects.create_user(username="other-rate-user", password="pw")
        ConnectionRateLimit.record_attempt("10.0.0.1", self.user)  # same user
        ConnectionRateLimit.record_attempt("10.0.0.1", other)  # neither
        ConnectionRateLimit.record_attempt("127.0.0.1", other)  # same IP

        ip_blocked = ConnectionRateLimit.check_rate_limit(
            "127.0.0.1", self.user, max_attempts=1
        )
        user_blocked = ConnectionRateLimit.check_rate_limit(
            "192.168.0.1", self.user, max_attempts=1
        )
        clear = ConnectionRateLimit.check_rate_limit(
            "192.168.0.1", AnonymousUser(), max_attempts=1
        )

        self.assertEqual((False, 1), ip_blocked)
        self.assertEqual((False, 1), user_blocked)
        self.assertEqual((True, 0), clear)

    def test_attempts_outside_the_window_are_not_counted(self):
        old = ConnectionRateLimit.record_attempt("127.0.0.1", self.user)
        ConnectionRateLimit.objects.filter(pk=old.pk).update(
            attempt_time=timezone.now() - timezone.timedelta(minutes=10)
        )

        self.assertEqual(
            (True, 0),
            ConnectionRateLimit.check_rate_limit(
                "127.0.0.1", self.user, max_attempts=1, window_minutes=5
            ),
        )

    def _expired_attempts(self, count):
        for _ in range(count):
            ConnectionRateLimit.objects.create(ip_address="10.9.9.9")
        ConnectionRateLimit.objects.filter(ip_address="10.9.9.9").update(
            attempt_time=timezone.now() - timezone.timedelta(days=8)
        )

    @patch("django_aws_api_gateway_websockets.models.secrets.randbelow", return_value=0)
    def test_recording_an_attempt_sometimes_deletes_expired_rows(self, _randbelow):
        self._expired_attempts(3)

        ConnectionRateLimit.record_attempt("127.0.0.1", self.user)

        self.assertFalse(
            ConnectionRateLimit.objects.filter(ip_address="10.9.9.9").exists()
        )
        self.assertEqual(1, ConnectionRateLimit.objects.count())

    @patch("django_aws_api_gateway_websockets.models.secrets.randbelow", return_value=1)
    def test_most_attempts_leave_expired_rows_alone(self, _randbelow):
        self._expired_attempts(3)

        ConnectionRateLimit.record_attempt("127.0.0.1", self.user)

        self.assertEqual(
            3, ConnectionRateLimit.objects.filter(ip_address="10.9.9.9").count()
        )

    @patch("django_aws_api_gateway_websockets.models.secrets.randbelow", return_value=0)
    def test_one_purge_deletes_at_most_one_batch(self, _randbelow):
        self._expired_attempts(5)

        with patch(
            "django_aws_api_gateway_websockets.models.RATE_LIMIT_PURGE_BATCH", 2
        ):
            ConnectionRateLimit.record_attempt("127.0.0.1", self.user)

        self.assertEqual(
            3, ConnectionRateLimit.objects.filter(ip_address="10.9.9.9").count()
        )

    @patch("django_aws_api_gateway_websockets.models.secrets.randbelow", return_value=0)
    def test_a_purge_never_deletes_rows_inside_the_retention_period(self, _randbelow):
        recent = ConnectionRateLimit.objects.create(ip_address="10.8.8.8")
        ConnectionRateLimit.objects.filter(pk=recent.pk).update(
            attempt_time=timezone.now() - timezone.timedelta(days=6)
        )

        ConnectionRateLimit.record_attempt("127.0.0.1", self.user)

        self.assertTrue(ConnectionRateLimit.objects.filter(pk=recent.pk).exists())

    @patch("django_aws_api_gateway_websockets.models.secrets.randbelow", return_value=0)
    def test_a_failing_purge_does_not_stop_the_attempt_being_recorded(self, _randbelow):
        with patch.object(
            ConnectionRateLimit, "_purge_expired", side_effect=DatabaseError("busy")
        ):
            with self.assertLogs(
                "django_aws_api_gateway_websockets.models", level="ERROR"
            ):
                attempt = ConnectionRateLimit.record_attempt("127.0.0.1", self.user)

        self.assertTrue(ConnectionRateLimit.objects.filter(pk=attempt.pk).exists())


class WebSocketSessionMessageSizeTestCase(TestCase):
    def setUp(self):
        self.api_gateway = ApiGateway.objects.create(
            api_name="Message Size Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            deployment_id="",
        )

    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_raises_value_error_when_message_too_large(self):
        obj = WebSocketSession.objects.create(
            connection_id="ABC-123-LARGE",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )

        with self.assertRaises(ValueError):
            obj.send_message({"message": "x" * (1024 * 128)})


class RunsAwsCallsAtOnceMixin:
    """Run the AWS calls that a save or delete queues for commit as soon as it queues them.

    A ``TestCase`` wraps each test in a transaction that never commits, so a queued call
    would not run. These tests cover what the sync does, and ``AwsCallsAfterCommitTestCase``
    covers when it runs.
    """

    def setUp(self):
        super().setUp()
        patcher = patch(
            "django_aws_api_gateway_websockets.models.run_aws_after_commit",
            side_effect=lambda operation: operation(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class GetBoto3ClientTestCase(SimpleTestCase):
    def setUp(self):
        clear_boto3_client_cache()
        self.addCleanup(clear_boto3_client_cache)

    @override_settings(
        AWS_IAM_PROFILE=None,
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_GATEWAY_REGION_NAME="",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_region_is_required_to_use_machine_iam(self, mock_boto3):
        """Test what happens when there are not enough credentials

        :param MagicMock mock_boto3:
        :return:
        """
        with self.assertRaises(RuntimeError) as re:
            get_boto3_client("s3")
            self.assertEqual(
                "AWS_GATEWAY_REGION_NAME must be set within settings.py", str(re)
            )

    @override_settings(
        AWS_IAM_PROFILE="FakeIAMProfile",
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_GATEWAY_REGION_NAME=None,
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_boto3_connection_support_named_profiles(self, mock_boto3):
        """Named profiles are supported via the settings.py variable AWS_IAM_PROFILE.

        :param MagicMock mock_boto3:
        :return:
        """
        service = "s3"
        res = get_boto3_client(service)
        mock_boto3.Session.assert_called_with(profile_name=settings.AWS_IAM_PROFILE)
        mock_boto3.Session.return_value.client.assert_called_with(service, config=ANY)
        self.assertEqual(res, mock_boto3.Session.return_value.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_GATEWAY_REGION_NAME="eu-west-1",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_connection_made_if_AWS_GATEWAY_REGION_NAME_given_but_no_other_credentials(
        self, mock_boto3
    ):
        """This would be an example of the project running on an EC2 instance with a IAM profile assigned to it

        :param MagicMock mock_boto3:
        :return:
        """
        res = get_boto3_client("s3")
        mock_boto3.client.assert_called_with("s3", region_name="eu-west-1", config=ANY)

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_GATEWAY_REGION_NAME="eu-west-1",
    )
    @patch("django_aws_api_gateway_websockets.models.boto3")
    def test_additional_kwargs_are_passed_into_the_connection(self, mock_boto3):
        """Any additional kwargs passed into the function should be passed into the boto.client invocation

        :param MagicMock mock_boto3:
        :return:
        """
        res = get_boto3_client("s3", another="param")
        mock_boto3.client.assert_called_with(
            "s3", region_name="eu-west-1", another="param", config=ANY
        )

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID="my-access-key",
        AWS_SECRET_ACCESS_KEY="my-secret-key",
        AWS_GATEWAY_REGION_NAME="eu-west-1",
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
            region_name=settings.AWS_GATEWAY_REGION_NAME,
            config=ANY,
        )

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID="my-access-key",
        AWS_SECRET_ACCESS_KEY="my-secret-key",
        AWS_GATEWAY_REGION_NAME="eu-west-1",
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
            region_name=settings.AWS_GATEWAY_REGION_NAME,
            config=ANY,
        )

        self.assertEqual(res, mock_boto3.client.return_value)

    @override_settings(
        AWS_ACCESS_KEY_ID="my-access-key",
        AWS_SECRET_ACCESS_KEY="my-secret-key",
        AWS_GATEWAY_REGION_NAME="",
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
            str(e.exception),
            "AWS_GATEWAY_REGION_NAME or AWS_REGION_NAME must be set within settings.py",
        )


@override_settings(
    AWS_IAM_PROFILE=None,
    AWS_ACCESS_KEY_ID=None,
    AWS_SECRET_ACCESS_KEY=None,
    AWS_GATEWAY_REGION_NAME="eu-west-1",
)
@patch("django_aws_api_gateway_websockets.models.boto3")
class Boto3ClientCacheTestCase(SimpleTestCase):
    def setUp(self):
        clear_boto3_client_cache()
        self.addCleanup(clear_boto3_client_cache)

    def test_the_client_has_short_timeouts_and_bounded_retries(self, mock_boto3):
        get_boto3_client()

        config = mock_boto3.client.call_args.kwargs["config"]
        self.assertEqual(5, config.connect_timeout)
        self.assertEqual(20, config.read_timeout)
        self.assertEqual({"mode": "standard", "max_attempts": 3}, config.retries)

    def test_a_config_passed_in_is_used_as_it_is(self, mock_boto3):
        config = Config(connect_timeout=1, read_timeout=2)

        get_boto3_client("apigatewaymanagementapi", config=config)

        self.assertIs(config, mock_boto3.client.call_args.kwargs["config"])

    def test_the_same_arguments_reuse_one_client(self, mock_boto3):
        mock_boto3.client.side_effect = lambda *args, **kwargs: MagicMock()

        first = get_boto3_client()
        second = get_boto3_client()

        self.assertIs(first, second)
        mock_boto3.client.assert_called_once()

    def test_a_client_made_with_an_equal_config_is_reused(self, mock_boto3):
        mock_boto3.client.side_effect = lambda *args, **kwargs: MagicMock()

        first = get_boto3_client(config=Config(connect_timeout=1, read_timeout=2))
        second = get_boto3_client(config=Config(connect_timeout=1, read_timeout=2))
        other = get_boto3_client(config=Config(connect_timeout=1, read_timeout=3))

        self.assertIs(first, second)
        self.assertIsNot(first, other)

    def test_a_different_endpoint_or_service_gets_its_own_client(self, mock_boto3):
        mock_boto3.client.side_effect = lambda *args, **kwargs: MagicMock()

        one = get_boto3_client("apigatewaymanagementapi", endpoint_url="https://a")
        two = get_boto3_client("apigatewaymanagementapi", endpoint_url="https://b")
        three = get_boto3_client()

        self.assertEqual(3, len({id(one), id(two), id(three)}))

    def test_a_changed_credential_setting_builds_a_new_client(self, mock_boto3):
        mock_boto3.client.side_effect = lambda *args, **kwargs: MagicMock()
        first = get_boto3_client()

        with override_settings(AWS_GATEWAY_REGION_NAME="eu-west-2"):
            second = get_boto3_client()

        self.assertIsNot(first, second)

    def test_a_forked_process_does_not_share_the_parents_client(self, mock_boto3):
        mock_boto3.client.side_effect = lambda *args, **kwargs: MagicMock()
        first = get_boto3_client()

        with patch(
            "django_aws_api_gateway_websockets.models.os.getpid", return_value=1
        ):
            second = get_boto3_client()

        self.assertIsNot(first, second)

    def test_clearing_the_cache_builds_a_new_client(self, mock_boto3):
        mock_boto3.client.side_effect = lambda *args, **kwargs: MagicMock()
        first = get_boto3_client()

        clear_boto3_client_cache()

        self.assertIsNot(first, get_boto3_client())

    def test_a_failure_to_build_a_client_is_not_cached(self, mock_boto3):
        with override_settings(AWS_GATEWAY_REGION_NAME="", AWS_REGION_NAME=""):
            with self.assertRaises(RuntimeError):
                get_boto3_client()

        self.assertIsNotNone(get_boto3_client())


class ApiGatewaySimpleTestCase(SimpleTestCase):
    def setUp(self):
        # Claiming the record is a database write. The integration tests cover it.
        for name in ("_claim_for_creation", "_release_claim"):
            patcher = patch.object(ApiGateway, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test__str___returns_api_name(self):
        """The __str__ method should return the value of api_name"""
        self.assertEqual("My Api", str(ApiGateway(api_name="My Api")))

    # --- provisioning status

    def test_effective_status_is_the_stored_status_once_provisioning_has_started(self):
        for status in ApiGateway.ProvisioningStatus.values:
            if status == ApiGateway.ProvisioningStatus.PENDING:
                continue
            with self.subTest(status=status):
                obj = ApiGateway(provisioning_status=status, api_created=True)

                self.assertEqual(status, obj.effective_provisioning_status)

    def test_effective_status_treats_older_and_hand_registered_rows_as_complete(self):
        """Rows from before the status existed are PENDING with the booleans set."""
        pending = ApiGateway()
        created = ApiGateway(api_created=True)
        with_domain = ApiGateway(api_created=True, custom_domain_created=True)

        self.assertEqual("pending", pending.effective_provisioning_status)
        self.assertEqual("deployed", created.effective_provisioning_status)
        self.assertEqual("mapped", with_domain.effective_provisioning_status)

    def test_needs_api_creation_and_needs_custom_domain(self):
        expected = {
            "pending": (True, False),
            "api_created": (True, False),
            "routes_created": (True, False),
            "deployed": (False, True),
            "domain_created": (False, True),
            "mapped": (False, False),
        }
        for status, (api, domain) in expected.items():
            with self.subTest(status=status):
                obj = ApiGateway(provisioning_status=status)

                self.assertIs(api, obj.needs_api_creation)
                self.assertIs(domain, obj.needs_custom_domain)

    def test_a_row_registered_by_hand_needs_neither(self):
        obj = ApiGateway(api_created=True, custom_domain_created=True)

        self.assertFalse(obj.needs_api_creation)
        self.assertFalse(obj.needs_custom_domain)

    # --- create_gateway

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_create_gateway__when_api_already_created(self, mocked_get_boto3_client):
        """Should return False without trying to create the API"""
        for obj in (
            ApiGateway(api_name="My Api", api_created=True),
            ApiGateway(api_name="My Api", provisioning_status="deployed"),
            ApiGateway(api_name="My Api", provisioning_status="mapped"),
        ):
            with self.subTest(status=obj.provisioning_status):
                self.assertIs(False, obj.create_gateway())

        self.assertEqual(0, mocked_get_boto3_client.call_count)

    def _gateway(self, **kwargs):
        defaults = dict(
            pk=12,
            api_name="My Api",
            target_base_endpoint="https://example.com/",
        )
        defaults.update(kwargs)
        return ApiGateway(**defaults)

    def _record_saves(self, obj, mocked_save):
        """Capture the status and fields each save() writes, in order."""
        log = []

        def save(**kwargs):
            log.append((obj.provisioning_status, kwargs.get("update_fields")))

        mocked_save.side_effect = save
        return log

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
        obj = self._gateway(api_created=False)
        route_1 = ApiGatewayAdditionalRoute(deployed=True)
        route_2 = ApiGatewayAdditionalRoute(
            deployed=False, api_gateway=obj, integration_url="https://example.com/foo"
        )
        mocked_additional_routes.all.return_value = [route_1, route_2]
        log = self._record_saves(obj, mocked_save)

        self.assertFalse(obj.api_created)
        self.assertIs(True, obj.create_gateway())

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
        # Progress is written after each AWS step, not once at the end
        self.assertEqual(
            ["api_created", "routes_created", "deployed"],
            [status for status, _ in log],
        )
        self.assertTrue(
            {"api_created", "provisioning_status", "api_id", "api_endpoint"}
            <= set(log[0][1])
        )
        self.assertEqual("deployed", obj.provisioning_status)
        self.assertEqual("", obj.last_error)

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
        """When an exception is raised during create_api the other methods should not be called, api_created
        stays False, and the error is recorded
        """
        obj = self._gateway(api_created=False)
        mocked___create_api.side_effect = Exception("Unexpected Error")

        with self.assertRaises(Exception) as e:
            obj.create_gateway()

        self.assertEqual("Unexpected Error", str(e.exception))
        mocked_get_boto3_client.assert_called_with()
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        self.assertFalse(obj.api_created)
        self.assertEqual("pending", obj.provisioning_status)
        self.assertEqual("Exception", obj.last_error)
        self.assertEqual(0, mocked__create_routes.call_count)
        self.assertEqual(0, mocked__create_stage_and_deploy.call_count)
        mocked_save.assert_called_once_with(update_fields=["last_error", "updated_on"])

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
        """After a failure in _create_routes the API exists (api_created is True, so it is not created twice) but
        the status says the routes are not done, so it can be resumed, and the error is recorded
        """
        obj = self._gateway(api_created=False)
        mocked__create_routes.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}}, "apigateway"
        )

        with self.assertRaises(ClientError) as e:
            obj.create_gateway()

        self.assertTrue(obj.api_created)
        self.assertEqual("api_created", obj.provisioning_status)
        self.assertEqual("ClientError: ABC123", obj.last_error)
        self.assertTrue(obj.needs_api_creation)
        self.assertEqual(
            "An error occurred (ABC123) when calling the apigateway operation: Actual Error Here",
            str(e.exception),
        )
        mocked___create_api.assert_called_with(mocked_get_boto3_client.return_value)
        mocked__create_routes.assert_called_with(mocked_get_boto3_client.return_value)
        self.assertEqual(0, mocked__create_stage_and_deploy.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "additional_routes")
    @patch.object(ApiGateway, "save")
    def test_create_gateway__when__create_stage_and_deploy_clienterror(
        self,
        mocked_save,
        mocked_additional_routes,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        """After a failure creating the stage the routes are recorded as done and the gateway is not deployed"""
        mocked_additional_routes.all.return_value = []
        obj = self._gateway(api_created=False)
        mocked__create_stage_and_deploy.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}}, "apigateway"
        )

        with self.assertRaises(ClientError):
            obj.create_gateway()

        self.assertTrue(obj.api_created)
        self.assertEqual("routes_created", obj.provisioning_status)
        self.assertEqual("ClientError: ABC123", obj.last_error)
        self.assertTrue(obj.needs_api_creation)
        mocked__create_stage_and_deploy.assert_called_with(
            mocked_get_boto3_client.return_value
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "save")
    def test_a_failure_to_record_the_error_does_not_hide_the_original_error(
        self,
        mocked_save,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        obj = self._gateway(api_created=False)
        mocked__create_routes.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "x"}}, "apigateway"
        )
        calls = []

        def save(**kwargs):
            calls.append(kwargs["update_fields"])
            if "last_error" in kwargs["update_fields"] and obj.last_error:
                raise RuntimeError("database is down")

        mocked_save.side_effect = save

        with self.assertRaises(ClientError):
            obj.create_gateway()

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "_existing_route_keys")
    @patch.object(ApiGateway, "additional_routes")
    @patch.object(ApiGateway, "save")
    def test_create_gateway_resumes_from_api_created_without_creating_the_api_again(
        self,
        mocked_save,
        mocked_additional_routes,
        mocked__existing_route_keys,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        obj = self._gateway(
            api_created=True, provisioning_status="api_created", api_id="abc"
        )
        mocked__existing_route_keys.return_value = {"$connect", "report"}
        done = ApiGatewayAdditionalRoute(
            deployed=False,
            api_gateway=obj,
            route_key="report",
            integration_url="https://example.com/report",
        )
        todo = ApiGatewayAdditionalRoute(
            deployed=False,
            api_gateway=obj,
            route_key="other",
            integration_url="https://example.com/other",
        )
        mocked_additional_routes.all.return_value = [done, todo]

        self.assertIs(True, obj.create_gateway())

        self.assertEqual(0, mocked___create_api.call_count)
        client = mocked_get_boto3_client.return_value
        mocked__existing_route_keys.assert_called_once_with(client)
        mocked__create_routes.assert_called_once_with(
            client, skip_route_keys={"$connect", "report"}
        )
        # only the route that does not exist yet gets an integration
        client.create_integration.assert_called_once()
        self.assertEqual(
            "https://example.com/other",
            client.create_integration.call_args.kwargs["IntegrationUri"],
        )
        mocked__create_stage_and_deploy.assert_called_once_with(client)
        self.assertEqual("deployed", obj.provisioning_status)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_api")
    @patch.object(ApiGateway, "_create_routes")
    @patch.object(ApiGateway, "_create_stage_and_deploy")
    @patch.object(ApiGateway, "save")
    def test_create_gateway_resumes_from_routes_created_at_the_stage(
        self,
        mocked_save,
        mocked__create_stage_and_deploy,
        mocked__create_routes,
        mocked___create_api,
        mocked_get_boto3_client,
    ):
        obj = self._gateway(
            api_created=True, provisioning_status="routes_created", api_id="abc"
        )

        self.assertIs(True, obj.create_gateway())

        self.assertEqual(0, mocked___create_api.call_count)
        self.assertEqual(0, mocked__create_routes.call_count)
        # the stage may exist already if the failure came after it was created
        mocked__create_stage_and_deploy.assert_called_once_with(
            mocked_get_boto3_client.return_value, ignore_existing_stage=True
        )
        self.assertEqual("deployed", obj.provisioning_status)

    def test__existing_route_keys_follows_pagination(self):
        client = MagicMock()
        client.get_routes.side_effect = [
            {"Items": [{"RouteKey": "$connect"}], "NextToken": "t"},
            {"Items": [{"RouteKey": "report"}]},
        ]
        obj = ApiGateway(api_id="abc")

        self.assertEqual({"$connect", "report"}, obj._existing_route_keys(client))
        self.assertEqual("t", client.get_routes.call_args_list[1].kwargs["NextToken"])

    def test__create_routes_skips_route_keys_that_already_exist(self):
        client = MagicMock()
        client.create_integration.return_value = {"IntegrationId": "i1"}
        obj = ApiGateway(api_id="abc", target_base_endpoint="https://example.com/")

        obj._create_routes(client, skip_route_keys={"$connect", "$disconnect"})

        self.assertEqual(1, client.create_integration.call_count)
        self.assertEqual("$default", client.create_route.call_args.kwargs["RouteKey"])

    def test__create_stage_and_deploy_ignores_an_existing_stage_only_when_told_to(self):
        conflict = ClientError(
            {"Error": {"Code": "ConflictException", "Message": "exists"}}, "CreateStage"
        )
        client = MagicMock()
        client.create_stage.side_effect = conflict
        client.create_deployment.return_value = {"DeploymentId": "d1"}
        obj = ApiGateway(api_id="abc", stage_name="production")

        with self.assertRaises(ClientError):
            obj._create_stage_and_deploy(client)

        obj._create_stage_and_deploy(client, ignore_existing_stage=True)
        self.assertEqual("d1", obj.deployment_id)

    def test__create_stage_and_deploy_does_not_ignore_other_errors(self):
        client = MagicMock()
        client.create_stage.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "CreateStage"
        )
        obj = ApiGateway(api_id="abc", stage_name="production")

        with self.assertRaises(ClientError):
            obj._create_stage_and_deploy(client, ignore_existing_stage=True)

        client.create_deployment.assert_not_called()

    # --- create_custom_domain

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
        """When the API is not created, or only partly created, then a ValueError should be raised"""
        for status in ("pending", "api_created", "routes_created"):
            with self.subTest(status=status):
                obj = ApiGateway(
                    api_name="My Api",
                    api_created=False,
                    provisioning_status=status,
                    target_base_endpoint="https://example.com/",
                )

                with self.assertRaises(Exception) as e:
                    obj.create_custom_domain()

                self.assertEqual(
                    str(e.exception),
                    "The API needs to be created before calling this method",
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
        """The domain and the mapping are recorded as separate steps"""
        mocked__create_domain_name.return_value = {
            "DomainNameConfigurations": [
                {"ApiGatewayDomainName": "api-gateway.websocket.example.com"}
            ]
        }
        obj = ApiGateway(
            api_name="My Api",
            api_created=True,
            provisioning_status="deployed",
            certificate_arn="aws123:zxcv:3455",
            custom_domain_created=False,
            api_gateway_domain_name="",
            api_mapping_id="",
        )
        seen = []
        mocked_save.side_effect = lambda **kw: seen.append(
            (obj.provisioning_status, kw["update_fields"])
        )

        self.assertFalse(obj.custom_domain_created)
        obj.create_custom_domain()

        mocked_get_boto3_client.assert_called_with()
        mocked__create_domain_name.assert_called_with(
            mocked_get_boto3_client.return_value
        )
        mocked__create_api_mapping.assert_called_with(
            mocked_get_boto3_client.return_value
        )
        self.assertEqual(["domain_created", "mapped"], [status for status, _ in seen])
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
        """If the mapping fails the domain is still recorded, so the mapping can be retried alone"""
        mocked__create_api_mapping.side_effect = ClientError(
            {"Error": {"Code": "ABC123", "Message": "Actual Error Here"}}, "apigateway"
        )
        mocked__create_domain_name.return_value = {
            "DomainNameConfigurations": [
                {"ApiGatewayDomainName": "api-gateway.websocket.example.com"}
            ]
        }
        obj = ApiGateway(
            api_name="My Api",
            api_created=True,
            provisioning_status="deployed",
            certificate_arn="aws123:zxcv:3455",
            custom_domain_created=False,
            api_gateway_domain_name="",
            api_mapping_id="",
        )

        with self.assertRaises(ClientError) as ce:
            obj.create_custom_domain()

        mocked__create_domain_name.assert_called_with(
            mocked_get_boto3_client.return_value
        )
        self.assertTrue(obj.custom_domain_created)
        self.assertEqual("domain_created", obj.provisioning_status)
        self.assertEqual("ClientError: ABC123", obj.last_error)
        self.assertTrue(obj.needs_custom_domain)
        self.assertEqual(
            "api-gateway.websocket.example.com", obj.api_gateway_domain_name
        )
        self.assertEqual(
            str(ce.exception),
            "An error occurred (ABC123) when calling the apigateway operation: Actual Error Here",
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "_create_domain_name")
    @patch.object(ApiGateway, "_create_api_mapping")
    @patch.object(ApiGateway, "save")
    def test_create_custom_domain_resumes_at_the_mapping(
        self,
        mocked_save,
        mocked__create_api_mapping,
        mocked__create_domain_name,
        mocked_get_boto3_client,
    ):
        obj = ApiGateway(
            api_name="My Api",
            api_created=True,
            custom_domain_created=True,
            provisioning_status="domain_created",
            certificate_arn="aws123:zxcv:3455",
            api_gateway_domain_name="api-gateway.websocket.example.com",
        )

        obj.create_custom_domain()

        self.assertEqual(0, mocked__create_domain_name.call_count)
        mocked__create_api_mapping.assert_called_once_with(
            mocked_get_boto3_client.return_value
        )
        self.assertEqual("mapped", obj.provisioning_status)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @patch.object(ApiGateway, "save")
    def test_create_custom_domain_does_nothing_when_already_mapped(
        self, mocked_save, mocked_get_boto3_client
    ):
        obj = ApiGateway(
            api_name="My Api",
            provisioning_status="mapped",
            certificate_arn="aws123:zxcv:3455",
        )

        obj.create_custom_domain()

        self.assertEqual(0, mocked_get_boto3_client.call_count)
        self.assertEqual(0, mocked_save.call_count)

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
            target_base_endpoint="https://example.com/",
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
            Target=f"{obj.target_base_endpoint}default",
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
    @override_settings(WEBSOCKETS=ALLOWED_HOSTS_SETTING)
    def test_saving_a_route_to_a_host_that_is_not_listed_is_refused(self):
        from django.core.exceptions import ValidationError

        gateway = ApiGateway.objects.create(
            api_name="Host Gateway", target_base_endpoint="https://www.example.com/"
        )
        route = ApiGatewayAdditionalRoute(
            api_gateway=gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://evil.example.net/ws/",
        )

        with self.assertRaises(ValidationError):
            route.save()

        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    def test_saving_a_route_validates_it_even_with_no_host_setting(self):
        from django.core.exceptions import ValidationError

        gateway = ApiGateway.objects.create(
            api_name="Valid Gateway", target_base_endpoint="https://www.example.com/"
        )

        with self.assertRaises(ValidationError) as error:
            ApiGatewayAdditionalRoute.objects.create(
                api_gateway=gateway,
                name="Chat",
                route_key="chat",
                integration_url="not a url",
            )

        self.assertIn("integration_url", error.exception.message_dict)

    def test_a_save_with_update_fields_skips_validation(self):
        gateway = ApiGateway.objects.create(
            api_name="Update Gateway", target_base_endpoint="https://www.example.com/"
        )
        route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://www.example.com/ws/chat",
        )
        route.name = "Renamed"

        route.save(update_fields=["name"])

        route.refresh_from_db()
        self.assertEqual("Renamed", route.name)

    @override_settings(WEBSOCKETS=ALLOWED_HOSTS_SETTING)
    def test_saving_a_gateway_to_a_host_that_is_not_listed_is_refused(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as error:
            ApiGateway.objects.create(
                api_name="Bad Host Gateway",
                target_base_endpoint="https://evil.example.net/",
            )

        self.assertIn("target_base_endpoint", error.exception.message_dict)

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
        mocked_get_boto3_client.return_value.create_deployment.return_value = {
            "DeploymentId": "Deploy-ID-456"
        }

        obj = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.deployed_api_gateway,
            name="Alternative Route",
            route_key="another-route",
            integration_url="https://www.example.com/ws/other",
            deployed=False,
        )

        self.assertTrue(obj.deployed)
        self.deployed_api_gateway.refresh_from_db()
        self.assertEqual("Deploy-ID-456", self.deployed_api_gateway.deployment_id)

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

    @patch("django_aws_api_gateway_websockets.models.boto3")
    @override_settings(
        AWS_IAM_PROFILE=None,
        AWS_ACCESS_KEY_ID=None,
        AWS_SECRET_ACCESS_KEY=None,
        AWS_GATEWAY_REGION_NAME="eu-west-1",
    )
    def test_send_message_builds_the_client_once_for_a_gateway(self, mock_boto3):
        clear_boto3_client_cache()
        self.addCleanup(clear_boto3_client_cache)
        self.api_gateway.api_id = "API123"
        self.api_gateway.save(update_fields=["api_id"])
        sessions = [
            WebSocketSession.objects.create(
                connection_id=f"REUSE-{number}", api_gateway=self.api_gateway
            )
            for number in range(3)
        ]

        for session in sessions:
            session.send_message({"action": "example"})

        mock_boto3.client.assert_called_once()
        self.assertEqual(
            3, mock_boto3.client.return_value.post_to_connection.call_count
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_reads_only_the_gateway_columns_it_needs(
        self, mocked_get_boto3_client
    ):
        self.api_gateway.api_id = "API123"
        self.api_gateway.save(update_fields=["api_id"])
        WebSocketSession.objects.create(
            connection_id="ONLY-1", api_gateway=self.api_gateway
        )
        session = WebSocketSession.objects.get(connection_id="ONLY-1")

        with CaptureQueriesContext(connection) as queries:
            session.send_message({"action": "example"})

        self.assertEqual(1, len(queries))
        self.assertIn("api_id", queries[0]["sql"])
        self.assertNotIn("target_base_endpoint", queries[0]["sql"])
        self.assertEqual(
            "https://API123.execute-api.eu-west-1.amazonaws.com/production",
            mocked_get_boto3_client.call_args.kwargs["endpoint_url"],
        )
        # The partial row is not left on the session
        self.assertFalse(WebSocketSession.api_gateway.is_cached(session))

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_uses_a_gateway_that_is_already_loaded(
        self, mocked_get_boto3_client
    ):
        self.api_gateway.api_id = "API123"
        self.api_gateway.save(update_fields=["api_id"])
        WebSocketSession.objects.create(
            connection_id="LOADED-1", api_gateway=self.api_gateway
        )
        session = WebSocketSession.objects.select_related("api_gateway").get(
            connection_id="LOADED-1"
        )

        with self.assertNumQueries(0):
            session.send_message({"action": "example"})

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_to_a_session_with_no_gateway_raises_a_clear_error(
        self, mocked_get_boto3_client
    ):
        obj = WebSocketSession.objects.create(connection_id="NO-GATEWAY-1")

        with self.assertRaisesMessage(ValueError, "no API Gateway"):
            obj.send_message({"action": "example"})

        mocked_get_boto3_client.assert_not_called()

    def test_deleting_a_gateway_marks_its_sessions_disconnected(self):
        other = ApiGateway.objects.create(
            api_name="Other Gateway", target_base_endpoint="http://www.example2.com/"
        )
        mine = WebSocketSession.objects.create(
            connection_id="MINE-1", api_gateway=self.api_gateway
        )
        theirs = WebSocketSession.objects.create(
            connection_id="THEIRS-1", api_gateway=other
        )

        self.api_gateway.delete()

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertFalse(mine.connected)
        self.assertIsNone(mine.api_gateway)
        self.assertTrue(theirs.connected)

    def test_a_queryset_delete_of_gateways_marks_their_sessions_disconnected(self):
        mine = WebSocketSession.objects.create(
            connection_id="MINE-1", api_gateway=self.api_gateway
        )

        ApiGateway.objects.filter(pk=self.api_gateway.pk).delete()

        mine.refresh_from_db()
        self.assertFalse(mine.connected)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
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
                f"{settings.AWS_GATEWAY_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
            ),
        )
        mocked_get_boto3_client.return_value.post_to_connection.assert_called_with(
            Data=json.dumps(data), ConnectionId=obj.connection_id
        )
        self.assertEqual(
            mocked_get_boto3_client.return_value.post_to_connection.return_value, res
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
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
                f"{settings.AWS_GATEWAY_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
            ),
        )
        mocked_get_boto3_client.return_value.post_to_connection.assert_called_with(
            Data=json.dumps(data), ConnectionId=obj.connection_id
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
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
                f"{settings.AWS_GATEWAY_REGION_NAME}.amazonaws.com/{obj.api_gateway.stage_name}"
            ),
        )


class WebSocketSessionQuerySetIntegrationTestCase(TestCase):
    def setUp(self) -> None:
        self.api_gateway = ApiGateway.objects.create(
            api_name="QuerySet Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            deployment_id="",
            api_id="API123",
            stage_name="production",
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_sends_to_connected_sessions_only(
        self,
        mocked_get_boto3_client,
    ):
        connected_session = WebSocketSession.objects.create(
            connection_id="CONNECTED-123",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        WebSocketSession.objects.create(
            connection_id="DISCONNECTED-123",
            channel_name="My-Channel",
            connected=False,
            api_gateway=self.api_gateway,
        )
        data = {"action": "example", "msg": "Test Me"}

        result = WebSocketSession.objects.filter(
            channel_name="My-Channel",
        ).send_message(data)

        mocked_get_boto3_client.assert_called_once()
        self.assertEqual(
            ("apigatewaymanagementapi",), mocked_get_boto3_client.call_args.args
        )
        self.assertEqual(
            "https://API123.execute-api.eu-west-1.amazonaws.com/production",
            mocked_get_boto3_client.call_args.kwargs["endpoint_url"],
        )
        mocked_get_boto3_client.return_value.post_to_connection.assert_called_once_with(
            Data=json.dumps(data),
            ConnectionId=connected_session.connection_id,
        )
        self.assertEqual(
            [mocked_get_boto3_client.return_value.post_to_connection.return_value],
            result,
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_skips_sessions_with_no_gateway_and_warns_once(
        self,
        mocked_get_boto3_client,
    ):
        for number in (1, 2):
            WebSocketSession.objects.create(
                connection_id=f"NO-GATEWAY-{number}", channel_name="My-Channel"
            )
        WebSocketSession.objects.create(
            connection_id="WITH-GATEWAY-1",
            channel_name="My-Channel",
            api_gateway=self.api_gateway,
        )

        with self.assertLogs(
            "django_aws_api_gateway_websockets.models", level="WARNING"
        ) as logs:
            result = WebSocketSession.objects.filter(
                channel_name="My-Channel"
            ).send_message({"action": "example"})

        self.assertEqual(1, len(logs.records))
        self.assertIn("2 sessions", logs.output[0])
        self.assertEqual(
            "https://API123.execute-api.eu-west-1.amazonaws.com/production",
            mocked_get_boto3_client.call_args.kwargs["endpoint_url"],
        )
        mocked_get_boto3_client.assert_called_once()
        post = mocked_get_boto3_client.return_value.post_to_connection
        post.assert_called_once_with(
            Data=json.dumps({"action": "example"}), ConnectionId="WITH-GATEWAY-1"
        )
        self.assertEqual([post.return_value], result)
        self.assertEqual(
            2,
            WebSocketSession.objects.filter(
                connection_id__startswith="NO-GATEWAY", connected=True
            ).count(),
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_marks_gone_connections_as_disconnected(
        self,
        mocked_get_boto3_client,
    ):
        mocked_get_boto3_client.return_value.post_to_connection.side_effect = (
            ClientError(
                {"Error": {"Code": "GoneException", "Message": "Gone"}},
                "apigateway",
            )
        )
        session = WebSocketSession.objects.create(
            connection_id="GONE-123",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )

        result = WebSocketSession.objects.filter(
            channel_name="My-Channel",
        ).send_message({"action": "example"})

        session.refresh_from_db()
        self.assertFalse(session.connected)
        self.assertEqual([], result)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_does_not_abort_on_non_gone_client_errors(
        self,
        mocked_get_boto3_client,
    ):
        """A throttled or failing recipient must not stop later recipients."""
        post = mocked_get_boto3_client.return_value.post_to_connection
        post.side_effect = [
            ClientError(
                {"Error": {"Code": "LimitExceededException", "Message": "Slow"}},
                "apigateway",
            ),
            {"ok": True},
        ]
        for connection_id in ("ERROR-123", "OK-456"):
            WebSocketSession.objects.create(
                connection_id=connection_id,
                channel_name="My-Channel",
                connected=True,
                api_gateway=self.api_gateway,
            )

        with self.assertLogs(
            "django_aws_api_gateway_websockets.models", level="WARNING"
        ):
            result = (
                WebSocketSession.objects.filter(channel_name="My-Channel")
                .order_by("connection_id")
                .send_message({"action": "example"})
            )

        self.assertEqual(2, post.call_count)
        self.assertEqual([{"ok": True}], result)
        self.assertEqual(2, WebSocketSession.objects.filter(connected=True).count())

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_marks_all_gone_sessions_in_one_update(
        self,
        mocked_get_boto3_client,
    ):
        mocked_get_boto3_client.return_value.post_to_connection.side_effect = (
            ClientError(
                {"Error": {"Code": "GoneException", "Message": "Gone"}},
                "apigateway",
            )
        )
        for connection_id in ("GONE-1", "GONE-2", "GONE-3"):
            WebSocketSession.objects.create(
                connection_id=connection_id,
                channel_name="My-Channel",
                connected=True,
                api_gateway=self.api_gateway,
            )

        # 1 select for the rows + 1 bulk update, regardless of recipient count.
        with self.assertNumQueries(2):
            WebSocketSession.objects.filter(channel_name="My-Channel").send_message(
                {"action": "example"}
            )

        self.assertFalse(WebSocketSession.objects.filter(connected=True).exists())

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_uses_each_sessions_own_gateway(
        self,
        mocked_get_boto3_client,
    ):
        other_gateway = ApiGateway.objects.create(
            api_name="Other Gateway",
            api_description="A second api gateway",
            target_base_endpoint="http://www.example2.com/",
            deployment_id="",
            api_id="OTHER99",
            stage_name="staging",
        )
        clients = {}

        def fake_client(service, endpoint_url, **kwargs):
            return clients.setdefault(endpoint_url, MagicMock())

        mocked_get_boto3_client.side_effect = fake_client
        WebSocketSession.objects.create(
            connection_id="A-1",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        WebSocketSession.objects.create(
            connection_id="B-1",
            channel_name="My-Channel",
            connected=True,
            api_gateway=other_gateway,
        )

        WebSocketSession.objects.filter(channel_name="My-Channel").send_message(
            {"action": "example"}
        )

        first = clients["https://API123.execute-api.eu-west-1.amazonaws.com/production"]
        second = clients["https://OTHER99.execute-api.eu-west-1.amazonaws.com/staging"]
        first.post_to_connection.assert_called_once_with(
            Data=json.dumps({"action": "example"}), ConnectionId="A-1"
        )
        second.post_to_connection.assert_called_once_with(
            Data=json.dumps({"action": "example"}), ConnectionId="B-1"
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_raises_value_error_when_message_too_large(
        self,
        mocked_get_boto3_client,
    ):
        WebSocketSession.objects.create(
            connection_id="BIG-1",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )

        with self.assertRaises(ValueError):
            WebSocketSession.objects.filter(channel_name="My-Channel").send_message(
                {"message": "x" * (1024 * 128)}
            )

        mocked_get_boto3_client.return_value.post_to_connection.assert_not_called()

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_configures_client_timeouts_retries_and_pool(
        self,
        mocked_get_boto3_client,
    ):
        for connection_id in ("T-1", "T-2", "T-3"):
            WebSocketSession.objects.create(
                connection_id=connection_id,
                channel_name="My-Channel",
                connected=True,
                api_gateway=self.api_gateway,
            )

        WebSocketSession.objects.filter(channel_name="My-Channel").send_message(
            {"action": "example"}, max_workers=2
        )

        config = mocked_get_boto3_client.call_args.kwargs["config"]
        self.assertEqual(2, config.max_pool_connections)
        self.assertEqual(BROADCAST_CONNECT_TIMEOUT, config.connect_timeout)
        self.assertEqual(BROADCAST_READ_TIMEOUT, config.read_timeout)
        self.assertEqual("standard", config.retries["mode"])

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_pool_is_no_larger_than_recipient_count(
        self,
        mocked_get_boto3_client,
    ):
        WebSocketSession.objects.create(
            connection_id="ONLY-1",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )

        WebSocketSession.objects.filter(channel_name="My-Channel").send_message(
            {"action": "example"}
        )

        config = mocked_get_boto3_client.call_args.kwargs["config"]
        self.assertEqual(1, config.max_pool_connections)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_posts_concurrently(self, mocked_get_boto3_client):
        """Two posts can only both pass the barrier if they run at the same time."""
        barrier = threading.Barrier(2, timeout=5)

        def post_to_connection(Data, ConnectionId):
            barrier.wait()
            return {"id": ConnectionId}

        mocked_get_boto3_client.return_value.post_to_connection.side_effect = (
            post_to_connection
        )
        for connection_id in ("C-1", "C-2"):
            WebSocketSession.objects.create(
                connection_id=connection_id,
                channel_name="My-Channel",
                connected=True,
                api_gateway=self.api_gateway,
            )

        result = (
            WebSocketSession.objects.filter(channel_name="My-Channel")
            .order_by("connection_id")
            .send_message({"action": "example"}, max_workers=2)
        )

        self.assertEqual([{"id": "C-1"}, {"id": "C-2"}], result)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_with_one_worker_posts_in_order(self, mocked_get_boto3_client):
        for connection_id in ("O-1", "O-2", "O-3"):
            WebSocketSession.objects.create(
                connection_id=connection_id,
                channel_name="My-Channel",
                connected=True,
                api_gateway=self.api_gateway,
            )

        (
            WebSocketSession.objects.filter(channel_name="My-Channel")
            .order_by("connection_id")
            .send_message({"action": "example"}, max_workers=1)
        )

        sent = [
            c.kwargs["ConnectionId"]
            for c in mocked_get_boto3_client.return_value.post_to_connection.call_args_list
        ]
        self.assertEqual(["O-1", "O-2", "O-3"], sent)

    def test_send_message_rejects_fewer_than_one_worker(self):
        with self.assertRaises(ValueError):
            WebSocketSession.objects.all().send_message({}, max_workers=0)


class SerialiseMessageSimpleTestCase(SimpleTestCase):
    def test_returns_json_string_for_small_payload(self):
        self.assertEqual('{"a": 1}', serialise_message({"a": 1}))

    def test_raises_value_error_when_over_limit(self):
        with self.assertRaisesMessage(ValueError, "Message exceeds AWS limit"):
            serialise_message({"message": "x" * (1024 * 128)})


class GetRegionNameSimpleTestCase(SimpleTestCase):
    @override_settings(AWS_GATEWAY_REGION_NAME="", AWS_REGION_NAME="")
    def test_get_region_name_raises_when_no_region_is_configured(self):
        from django_aws_api_gateway_websockets.models import get_region_name

        with self.assertRaises(RuntimeError):
            get_region_name()

    @override_settings(AWS_GATEWAY_REGION_NAME="", AWS_REGION_NAME="eu-west-2")
    def test_get_region_name_falls_back_to_aws_region_name(self):
        from django_aws_api_gateway_websockets.models import get_region_name

        self.assertEqual("eu-west-2", get_region_name())


class IntegrationHostValidationSimpleTestCase(SimpleTestCase):
    """With ``allowed_integration_hosts`` set, an integration can only point at those hosts."""

    def _gateway(self, url):
        return ApiGateway(api_name="Valid API", target_base_endpoint=url)

    def _route(self, url):
        return ApiGatewayAdditionalRoute(
            name="Chat", route_key="chat", integration_url=url
        )

    @override_settings(WEBSOCKETS=ALLOWED_HOSTS_SETTING)
    def test_a_listed_host_is_accepted(self):
        for url in (
            "https://www.example.com/ws/",
            "https://WWW.EXAMPLE.COM:8443/ws/",
            "https://one.apps.example.com/ws/",
            "https://a.b.apps.example.com/ws/",
        ):
            with self.subTest(url=url):
                self._gateway(url).clean()
                self._route(url).clean()

    @override_settings(WEBSOCKETS=ALLOWED_HOSTS_SETTING)
    def test_a_host_that_is_not_listed_is_refused_on_the_field(self):
        from django.core.exceptions import ValidationError

        for url in (
            "https://evil.example.net/ws/",
            "https://www.example.com.evil.net/ws/",
            "https://apps.example.com/ws/",  # a wildcard does not match its own domain
            "https://notapps.example.com/ws/",
            "https://www.example.com@evil.net/ws/",
            "not a url",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValidationError) as gateway_error:
                    self._gateway(url).clean()
                self.assertIn(
                    "target_base_endpoint", gateway_error.exception.message_dict
                )
                with self.assertRaises(ValidationError) as route_error:
                    self._route(url).clean()
                self.assertIn("integration_url", route_error.exception.message_dict)

    @override_settings(WEBSOCKETS={})
    def test_any_host_is_accepted_when_the_setting_is_not_set(self):
        self._gateway("https://anything.example.net/ws/").clean()
        self._route("https://anything.example.net/ws/").clean()

    @override_settings(WEBSOCKETS=ALLOWED_HOSTS_SETTING)
    def test_a_gateway_without_an_endpoint_is_not_checked_here(self):
        self._gateway("").clean()

    @override_settings(WEBSOCKETS=ALLOWED_HOSTS_SETTING)
    def test_the_error_does_not_list_the_allowed_hosts(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as error:
            self._route("https://evil.example.net/").clean()

        self.assertNotIn("example.com", str(error.exception))


class ApiGatewayValidationTestCase(SimpleTestCase):
    def test_clean_raises_validation_error_for_invalid_domain_name(self):
        from django.core.exceptions import ValidationError

        obj = ApiGateway(
            api_name="Valid API",
            domain_name="-invalid.example.com",
            target_base_endpoint="https://www.example.com/",
        )

        with self.assertRaises(ValidationError) as context:
            obj.clean()

        self.assertIn("domain_name", context.exception.message_dict)

    def test_clean_raises_validation_error_for_invalid_api_name(self):
        from django.core.exceptions import ValidationError

        obj = ApiGateway(
            api_name="Invalid API!",
            domain_name="valid.example.com",
            target_base_endpoint="https://www.example.com/",
        )

        with self.assertRaises(ValidationError) as context:
            obj.clean()

        self.assertIn("api_name", context.exception.message_dict)

    def test_clean_allows_blank_domain_name_and_api_name(self):
        obj = ApiGateway(
            api_name="",
            domain_name="",
            target_base_endpoint="https://www.example.com/",
        )

        self.assertIsNone(obj.clean())


class ConnectionRateLimitBranchTestCase(TestCase):
    def test_check_rate_limit_skips_user_check_for_anonymous_user(self):
        anonymous_user = AnonymousUser()

        allowed, attempts = ConnectionRateLimit.check_rate_limit(
            ip_address="127.0.0.1",
            user=anonymous_user,
            max_attempts=1,
            window_minutes=5,
        )

        self.assertTrue(allowed)
        self.assertEqual(0, attempts)


class WebSocketSessionQuerySetBranchTestCase(TestCase):
    def setUp(self) -> None:
        self.api_gateway = ApiGateway.objects.create(
            api_name="QuerySet Branch Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            deployment_id="",
            api_id="API456",
            stage_name="production",
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_send_message_reuses_client_for_multiple_connected_sessions(
        self,
        mocked_get_boto3_client,
    ):
        first_session = WebSocketSession.objects.create(
            connection_id="CONNECTED-ONE",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        second_session = WebSocketSession.objects.create(
            connection_id="CONNECTED-TWO",
            channel_name="My-Channel",
            connected=True,
            api_gateway=self.api_gateway,
        )
        data = {"action": "example"}

        result = (
            WebSocketSession.objects.filter(
                channel_name="My-Channel",
            )
            .order_by("connection_id")
            .send_message(data)
        )

        mocked_get_boto3_client.assert_called_once()
        self.assertEqual(
            ("apigatewaymanagementapi",), mocked_get_boto3_client.call_args.args
        )
        self.assertEqual(
            "https://API456.execute-api.eu-west-1.amazonaws.com/production",
            mocked_get_boto3_client.call_args.kwargs["endpoint_url"],
        )
        mocked_get_boto3_client.return_value.post_to_connection.assert_has_calls(
            [
                call(Data=json.dumps(data), ConnectionId=first_session.connection_id),
                call(Data=json.dumps(data), ConnectionId=second_session.connection_id),
            ],
            any_order=True,
        )
        self.assertEqual(
            [
                mocked_get_boto3_client.return_value.post_to_connection.return_value,
                mocked_get_boto3_client.return_value.post_to_connection.return_value,
            ],
            result,
        )


class PostToConnectionSimpleTestCase(SimpleTestCase):
    def test_returns_sent_and_response_on_success(self):
        client = MagicMock()

        status, response = _post_to_connection(client, '{"a": 1}', "CONN-1")

        client.post_to_connection.assert_called_once_with(
            Data='{"a": 1}', ConnectionId="CONN-1"
        )
        self.assertEqual("sent", status)
        self.assertEqual(client.post_to_connection.return_value, response)

    def test_returns_gone_for_gone_exception(self):
        client = MagicMock()
        client.post_to_connection.side_effect = ClientError(
            {"Error": {"Code": "GoneException", "Message": "Gone"}}, "apigateway"
        )

        self.assertEqual(("gone", None), _post_to_connection(client, "{}", "CONN-1"))

    def test_returns_failed_and_logs_for_other_client_errors(self):
        client = MagicMock()
        client.post_to_connection.side_effect = ClientError(
            {"Error": {"Code": "ForbiddenException", "Message": "No"}}, "apigateway"
        )

        with self.assertLogs(
            "django_aws_api_gateway_websockets.models", level="WARNING"
        ) as logs:
            result = _post_to_connection(client, "{}", "CONN-1")

        self.assertEqual(("failed", None), result)
        self.assertIn("ForbiddenException", logs.output[0])

    def test_returns_failed_and_logs_for_botocore_errors(self):
        client = MagicMock()
        client.post_to_connection.side_effect = BotoCoreError()

        with self.assertLogs(
            "django_aws_api_gateway_websockets.models", level="WARNING"
        ):
            result = _post_to_connection(client, "{}", "CONN-1")

        self.assertEqual(("failed", None), result)


class ApiGatewayCreateGatewayResultTestCase(TestCase):
    """create_gateway reports whether it created the gateway, so the admin can tell"""

    def _gateway(self, **kwargs):
        defaults = {
            "api_name": "Result Gateway",
            "api_description": "A test api gateway",
            "target_base_endpoint": "https://example.com/ws/",
            "stage_name": "production",
        }
        defaults.update(kwargs)
        return ApiGateway.objects.create(**defaults)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_create_gateway_returns_true_when_it_creates_the_gateway(
        self, mocked_get_boto3_client
    ):
        client = mocked_get_boto3_client.return_value
        client.create_api.return_value = {"ApiId": "A1", "ApiEndpoint": "wss://x"}
        client.create_integration.return_value = {"IntegrationId": "i1"}
        client.create_deployment.return_value = {"DeploymentId": "d1"}
        obj = self._gateway()

        self.assertIs(True, obj.create_gateway())

        obj.refresh_from_db()
        self.assertTrue(obj.api_created)
        self.assertEqual("A1", obj.api_id)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_create_gateway_target_has_a_single_slash(self, mocked_get_boto3_client):
        client = mocked_get_boto3_client.return_value
        client.create_api.return_value = {"ApiId": "A1", "ApiEndpoint": "wss://x"}
        client.create_integration.return_value = {"IntegrationId": "i1"}
        client.create_deployment.return_value = {"DeploymentId": "d1"}

        self._gateway().create_gateway()

        self.assertEqual(
            "https://example.com/ws/default",
            client.create_api.call_args.kwargs["Target"],
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_create_gateway_without_a_target_endpoint_raises_before_calling_aws(
        self, mocked_get_boto3_client
    ):
        obj = self._gateway(target_base_endpoint=None)

        with self.assertRaisesMessage(ValueError, "target_base_endpoint"):
            obj.create_gateway()

        mocked_get_boto3_client.assert_not_called()
        obj.refresh_from_db()
        self.assertFalse(obj.api_created)

    def test_save_accepts_a_missing_target_endpoint(self):
        obj = self._gateway(target_base_endpoint=None)

        obj.refresh_from_db()
        self.assertIsNone(obj.target_base_endpoint)

    def test_save_adds_a_trailing_slash_once(self):
        obj = self._gateway(target_base_endpoint="https://example.com/ws")

        self.assertEqual("https://example.com/ws/", obj.target_base_endpoint)
        obj.save()
        self.assertEqual("https://example.com/ws/", obj.target_base_endpoint)


def _user(**kwargs):
    attributes = {
        "is_authenticated": True,
        "is_active": True,
        "is_staff": False,
        "is_superuser": False,
    }
    attributes.update(kwargs)
    return MagicMock(**attributes)


class ChannelPermissionAccessSimpleTestCase(SimpleTestCase):
    """The access levels that need no permission rules, so no database."""

    def test_str_shows_channel_and_access(self):
        obj = ChannelPermission(
            channel_name="admin", access=ChannelPermission.Access.STAFF_ONLY
        )

        self.assertEqual("admin (Staff only)", str(obj))

    def test_default_access_is_allow_all(self):
        self.assertEqual(ChannelPermission.Access.ALLOW_ALL, ChannelPermission().access)

    def test_allow_all_allows_everyone_including_anonymous(self):
        obj = ChannelPermission(access=ChannelPermission.Access.ALLOW_ALL)

        self.assertTrue(obj.allows(AnonymousUser()))
        self.assertTrue(obj.allows(None))
        self.assertTrue(obj.allows(_user()))

    def test_superuser_only(self):
        obj = ChannelPermission(access=ChannelPermission.Access.SUPERUSER_ONLY)

        self.assertTrue(obj.allows(_user(is_superuser=True)))
        self.assertFalse(obj.allows(_user(is_staff=True)))
        self.assertFalse(obj.allows(_user()))
        self.assertFalse(obj.allows(AnonymousUser()))
        self.assertFalse(obj.allows(None))
        self.assertFalse(obj.allows(_user(is_superuser=True, is_active=False)))

    def test_staff_only_allows_staff_and_superusers(self):
        obj = ChannelPermission(access=ChannelPermission.Access.STAFF_ONLY)

        self.assertTrue(obj.allows(_user(is_staff=True)))
        self.assertTrue(obj.allows(_user(is_superuser=True)))
        self.assertFalse(obj.allows(_user()))
        self.assertFalse(obj.allows(AnonymousUser()))
        self.assertFalse(obj.allows(_user(is_staff=True, is_active=False)))

    def test_unknown_access_value_denies(self):
        obj = ChannelPermission(access="something-new")

        self.assertFalse(obj.allows(_user(is_superuser=True)))

    def test_channel_name_validator_matches_the_view_pattern(self):
        for name in ("room-1", "tenant_456", "A1"):
            ChannelPermission(channel_name=name).clean_fields(exclude=["access"])
        for name in ("bad name", "semi;colon", "a/b", "a" * 129):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    ChannelPermission(channel_name=name).clean_fields(
                        exclude=["access"]
                    )


class ChannelPermissionRulesIntegrationTestCase(TestCase):
    """``Requires Django permissions``: OR across rules, AND within a rule."""

    def setUp(self):
        self.channel = ChannelPermission.objects.create(
            channel_name="reports",
            access=ChannelPermission.Access.PERMISSIONS,
        )
        self.view_user = Permission.objects.get(codename="view_user")
        self.view_group = Permission.objects.get(codename="view_group")
        self.view_permission = Permission.objects.get(codename="view_permission")

    def _rule(self, *permissions):
        rule = ChannelPermissionRule.objects.create(channel_permission=self.channel)
        rule.permissions.set(permissions)
        return rule

    def _user(self, *permissions, **kwargs):
        user = User.objects.create_user(
            username=f"u{User.objects.count()}", password="pw", **kwargs
        )
        user.user_permissions.set(permissions)
        return User.objects.get(pk=user.pk)  # drop the cached permissions

    def _allows(self, user):
        return ChannelPermission.objects.get(pk=self.channel.pk).allows(user)

    def test_no_rules_denies_everyone_except_superusers(self):
        self.assertFalse(self._allows(self._user(self.view_user)))
        self.assertTrue(self._allows(self._user(is_superuser=True)))

    def test_a_rule_with_no_permissions_never_matches(self):
        """An empty AND must not mean 'everyone'."""
        self._rule()

        self.assertFalse(self._allows(self._user(self.view_user)))

    def test_one_rule_with_one_permission(self):
        self._rule(self.view_user)

        self.assertTrue(self._allows(self._user(self.view_user)))
        self.assertFalse(self._allows(self._user(self.view_group)))
        self.assertFalse(self._allows(self._user()))

    def test_permissions_in_one_rule_are_anded(self):
        """User must have permission A and permission B."""
        self._rule(self.view_user, self.view_group)

        self.assertTrue(self._allows(self._user(self.view_user, self.view_group)))
        self.assertFalse(self._allows(self._user(self.view_user)))
        self.assertFalse(self._allows(self._user(self.view_group)))

    def test_separate_rules_are_ored(self):
        """User must have permission A or permission B."""
        self._rule(self.view_user)
        self._rule(self.view_group)

        self.assertTrue(self._allows(self._user(self.view_user)))
        self.assertTrue(self._allows(self._user(self.view_group)))
        self.assertTrue(self._allows(self._user(self.view_user, self.view_group)))
        self.assertFalse(self._allows(self._user(self.view_permission)))

    def test_and_within_a_rule_and_or_between_rules(self):
        """(A and B) or C"""
        self._rule(self.view_user, self.view_group)
        self._rule(self.view_permission)

        self.assertTrue(self._allows(self._user(self.view_user, self.view_group)))
        self.assertTrue(self._allows(self._user(self.view_permission)))
        self.assertFalse(self._allows(self._user(self.view_user)))
        self.assertFalse(self._allows(self._user(self.view_group)))

    def test_anonymous_and_inactive_users_are_denied(self):
        self._rule(self.view_user)

        self.assertFalse(self._allows(AnonymousUser()))
        self.assertFalse(self._allows(None))
        self.assertFalse(self._allows(self._user(self.view_user, is_active=False)))

    def test_superuser_passes_without_holding_the_permissions(self):
        self._rule(self.view_user, self.view_group)

        self.assertTrue(self._allows(self._user(is_superuser=True)))

    def test_rules_are_ignored_unless_access_is_permissions(self):
        self._rule(self.view_user)
        self.channel.access = ChannelPermission.Access.STAFF_ONLY
        self.channel.save()

        self.assertFalse(self._allows(self._user(self.view_user)))
        self.assertTrue(self._allows(self._user(is_staff=True)))

    def test_loading_the_rules_takes_a_fixed_number_of_queries(self):
        for _ in range(5):
            self._rule(self.view_user, self.view_group)
        channel = ChannelPermission.objects.get(pk=self.channel.pk)
        user = _user()
        user.has_perms.return_value = False

        # one query for the rules and one for their permissions, however many rules
        with self.assertNumQueries(2):
            channel.allows(user)

    def test_for_channel_returns_the_row_or_none(self):
        self.assertEqual(self.channel, ChannelPermission.for_channel("reports"))
        self.assertIsNone(ChannelPermission.for_channel("unlisted"))

    def test_channel_name_is_unique(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            ChannelPermission.objects.create(channel_name="reports")

    def test_rule_str_lists_its_permissions(self):
        rule = self._rule(self.view_user)

        self.assertIn("view_user", str(rule))


SECRET = "s3cr3t-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
OLD_SECRET = "0ld-" + "y" * 40
CONNECTION_PARAMETER = "integration.request.header.connectionId"
SECRET_PARAMETER = f"integration.request.header.{GATEWAY_SECRET_HEADER}"


class GatewaySecretSettingSimpleTestCase(SimpleTestCase):
    def test_no_secret_when_the_setting_is_absent_or_empty(self):
        for websockets in (None, {}, {"gateway_secret": ""}, {"gateway_secret": None}):
            with self.subTest(websockets=websockets):
                with override_settings(WEBSOCKETS=websockets):
                    self.assertEqual([], get_gateway_secrets())

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_a_string_is_one_secret(self):
        self.assertEqual([SECRET], get_gateway_secrets())

    @override_settings(WEBSOCKETS={"gateway_secret": [SECRET, OLD_SECRET, ""]})
    def test_a_list_gives_several_secrets_and_drops_blanks(self):
        """The first is sent to API Gateway. All are accepted, which allows rotation."""
        self.assertEqual([SECRET, OLD_SECRET], get_gateway_secrets())

    def test_integration_parameters_without_a_secret_are_unchanged(self):
        with override_settings(WEBSOCKETS=None):
            self.assertEqual(
                {CONNECTION_PARAMETER: "context.connectionId"},
                integration_request_parameters(),
            )

    @override_settings(WEBSOCKETS={"gateway_secret": [SECRET, OLD_SECRET]})
    def test_integration_parameters_send_the_first_secret_as_a_static_value(self):
        self.assertEqual(
            {
                CONNECTION_PARAMETER: "context.connectionId",
                SECRET_PARAMETER: f"'{SECRET}'",
            },
            integration_request_parameters(),
        )

    def test_a_secret_that_could_break_the_mapping_expression_is_refused(self):
        for bad in ("short", "has'quote" + "x" * 40, "has space" + "x" * 40, "a" * 31):
            with self.subTest(secret=bad):
                with override_settings(WEBSOCKETS={"gateway_secret": bad}):
                    with self.assertRaises(ValueError):
                        integration_request_parameters()

    def test_a_secret_with_a_newline_is_refused(self):
        """A secret read from a file often ends in a newline, which must not reach AWS."""
        for bad in (SECRET + "\n", SECRET + "\r\n", "\n" + SECRET, SECRET + "\n\n"):
            with self.subTest(secret=bad):
                with override_settings(WEBSOCKETS={"gateway_secret": bad}):
                    with self.assertRaisesMessage(ValueError, "newline"):
                        integration_request_parameters()

    def test_the_secret_pattern_matches_the_whole_value(self):
        from django_aws_api_gateway_websockets.models import GATEWAY_SECRET_PATTERN

        self.assertTrue(GATEWAY_SECRET_PATTERN.fullmatch(SECRET))
        self.assertIsNone(GATEWAY_SECRET_PATTERN.fullmatch(SECRET + "\n"))

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_create_routes_adds_the_secret_to_every_integration(self):
        client = MagicMock()
        client.create_integration.return_value = {"IntegrationId": "i1"}
        obj = ApiGateway(api_id="123456", target_base_endpoint="https://example.com/")

        obj._create_routes(client)

        self.assertEqual(3, client.create_integration.call_count)
        for integration_call in client.create_integration.call_args_list:
            self.assertEqual(
                f"'{SECRET}'",
                integration_call.kwargs["RequestParameters"][SECRET_PARAMETER],
            )

    @override_settings(WEBSOCKETS={"gateway_secret": SECRET})
    def test_additional_route_integration_carries_the_secret(self):
        client = MagicMock()
        client.create_integration.return_value = {"IntegrationId": "i1"}
        route = ApiGatewayAdditionalRoute(
            api_gateway=ApiGateway(api_id="123456"),
            route_key="report",
            integration_url="https://example.com/report",
        )

        route.create_route(client, deploy=False)

        self.assertEqual(
            f"'{SECRET}'",
            client.create_integration.call_args.kwargs["RequestParameters"][
                SECRET_PARAMETER
            ],
        )

    def test_additional_route_integration_has_no_secret_when_none_is_set(self):
        client = MagicMock()
        client.create_integration.return_value = {"IntegrationId": "i1"}
        route = ApiGatewayAdditionalRoute(
            api_gateway=ApiGateway(api_id="123456"),
            route_key="report",
            integration_url="https://example.com/report",
        )

        with override_settings(WEBSOCKETS=None):
            route.create_route(client, deploy=False)

        self.assertEqual(
            {CONNECTION_PARAMETER: "context.connectionId"},
            client.create_integration.call_args.kwargs["RequestParameters"],
        )


class WebSocketSessionGoneWritesTestCase(TestCase):
    """Marking a session gone must not write back stale values for other fields."""

    def setUp(self):
        self.api_gateway = ApiGateway.objects.create(
            api_name="Gone Gateway",
            api_description="A test api gateway",
            target_base_endpoint="http://www.example1.com/",
            api_id="API123",
            stage_name="production",
        )
        self.session = WebSocketSession.objects.create(
            connection_id="GONE-1",
            channel_name="room-1",
            connected=True,
            api_gateway=self.api_gateway,
        )

    def _gone(self, mocked_get_boto3_client):
        mocked_get_boto3_client.return_value.post_to_connection.side_effect = (
            ClientError(
                {"Error": {"Code": "GoneException", "Message": "Gone"}}, "apigateway"
            )
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_instance_send_message_gone_does_not_overwrite_other_fields(
        self, mocked_get_boto3_client
    ):
        self._gone(mocked_get_boto3_client)
        stale = WebSocketSession.objects.get(pk=self.session.pk)
        WebSocketSession.objects.filter(pk=self.session.pk).update(
            channel_name="room-9", request_count=42
        )

        stale.send_message({"a": 1})

        row = WebSocketSession.objects.get(pk=self.session.pk)
        self.assertFalse(row.connected)
        self.assertEqual("room-9", row.channel_name)
        self.assertEqual(42, row.request_count)
        self.assertFalse(stale.connected)  # the instance in memory agrees

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    @override_settings(AWS_GATEWAY_REGION_NAME="eu-west-1")
    def test_instance_send_message_gone_uses_one_write_and_refreshes_updated_on(
        self, mocked_get_boto3_client
    ):
        self._gone(mocked_get_boto3_client)
        obj = WebSocketSession.objects.select_related("api_gateway").get(
            pk=self.session.pk
        )
        before = obj.updated_on

        with self.assertNumQueries(1):
            obj.send_message({"a": 1})

        self.assertGreater(
            WebSocketSession.objects.get(pk=self.session.pk).updated_on, before
        )


class ApiGatewayProvisioningIntegrationTestCase(TestCase):
    """A half-built gateway is visible, keeps what AWS returned, and can be resumed."""

    def _gateway(self, **kwargs):
        defaults = {
            "api_name": "Resume Gateway",
            "target_base_endpoint": "https://example.com/ws/",
            "stage_name": "production",
        }
        defaults.update(kwargs)
        return ApiGateway.objects.create(**defaults)

    def _client(self):
        client = MagicMock()
        client.create_api.return_value = {"ApiId": "A1", "ApiEndpoint": "wss://x"}
        client.create_integration.return_value = {"IntegrationId": "i1"}
        client.create_deployment.return_value = {"DeploymentId": "d1"}
        return client

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_failure_part_way_keeps_the_api_id_and_shows_the_status(self, mocked):
        client = mocked.return_value = self._client()
        client.create_integration.side_effect = [
            {"IntegrationId": "i1"},
            ClientError(
                {"Error": {"Code": "Throttled", "Message": "x"}}, "CreateIntegration"
            ),
        ]
        obj = self._gateway()

        with self.assertRaises(ClientError):
            obj.create_gateway()

        obj = ApiGateway.objects.get(pk=obj.pk)
        self.assertEqual("A1", obj.api_id)  # the API is not orphaned
        self.assertTrue(obj.api_created)
        self.assertEqual("api_created", obj.provisioning_status)
        self.assertEqual("ClientError: Throttled", obj.last_error)
        self.assertEqual("", obj.deployment_id)
        self.assertTrue(obj.needs_api_creation)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_concurrent_run_does_not_create_a_second_api(self, mocked):
        """Another request that starts while the first is calling AWS is refused."""
        client = mocked.return_value = self._client()
        obj = self._gateway()
        rival = ApiGateway.objects.get(pk=obj.pk)
        rival_errors = []

        def rival_starts(**kwargs):
            try:
                rival.create_gateway()
            except ValueError as error:
                rival_errors.append(str(error))
            return {"ApiId": "A1", "ApiEndpoint": "wss://x"}

        client.create_api.side_effect = rival_starts

        self.assertTrue(obj.create_gateway())

        client.create_api.assert_called_once()
        self.assertEqual(1, len(rival_errors))
        self.assertIn("already being created", rival_errors[0])
        self.assertEqual(
            "deployed", ApiGateway.objects.get(pk=obj.pk).provisioning_status
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_record_another_request_is_creating_is_refused(self, mocked):
        client = mocked.return_value = self._client()
        obj = self._gateway()
        ApiGateway.objects.filter(pk=obj.pk).update(provisioning_status="creating")

        for copy in (obj, ApiGateway.objects.get(pk=obj.pk)):
            with self.subTest(stale_copy=copy is obj):
                with self.assertRaisesMessage(ValueError, "already being created"):
                    copy.create_gateway()

        client.create_api.assert_not_called()
        self.assertEqual(
            "creating", ApiGateway.objects.get(pk=obj.pk).provisioning_status
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_failure_before_the_api_exists_lets_the_next_run_start_again(
        self, mocked
    ):
        client = mocked.return_value = self._client()
        client.create_api.side_effect = [
            ClientError({"Error": {"Code": "Throttled"}}, "CreateApi"),
            {"ApiId": "A1", "ApiEndpoint": "wss://x"},
        ]
        obj = self._gateway()

        with self.assertRaises(ClientError):
            obj.create_gateway()

        stored = ApiGateway.objects.get(pk=obj.pk)
        self.assertEqual("pending", stored.provisioning_status)
        self.assertEqual("ClientError: Throttled", stored.last_error)
        self.assertTrue(stored.create_gateway())
        self.assertEqual(2, client.create_api.call_count)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_run_that_cannot_record_the_new_api_stays_claimed(self, mocked):
        """The API exists in AWS, so another run could create a duplicate. A person decides."""
        mocked.return_value = self._client()
        obj = self._gateway()

        with patch.object(ApiGateway, "_record", side_effect=DatabaseError("down")):
            with self.assertRaises(DatabaseError):
                obj.create_gateway()

        self.assertEqual(
            "creating", ApiGateway.objects.get(pk=obj.pk).provisioning_status
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_second_run_resumes_and_finishes(self, mocked):
        client = mocked.return_value = self._client()
        client.create_integration.side_effect = [
            {"IntegrationId": "i1"},
            ClientError(
                {"Error": {"Code": "Throttled", "Message": "x"}}, "CreateIntegration"
            ),
        ]
        obj = self._gateway()
        with self.assertRaises(ClientError):
            obj.create_gateway()

        # AWS now has the $connect route from the first run
        client.create_integration.side_effect = None
        client.create_integration.return_value = {"IntegrationId": "i2"}
        client.get_routes.return_value = {"Items": [{"RouteKey": "$connect"}]}
        obj = ApiGateway.objects.get(pk=obj.pk)

        self.assertIs(True, obj.create_gateway())

        obj = ApiGateway.objects.get(pk=obj.pk)
        self.assertEqual(1, client.create_api.call_count)  # no second API
        created = [c.kwargs["RouteKey"] for c in client.create_route.call_args_list]
        self.assertEqual(["$connect", "$disconnect", "$default"], created)
        self.assertEqual("deployed", obj.provisioning_status)
        self.assertEqual("d1", obj.deployment_id)
        self.assertEqual("", obj.last_error)
        self.assertFalse(obj.needs_api_creation)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_an_invalid_record_fails_before_anything_is_created_in_aws(self, mocked):
        obj = ApiGateway(
            api_name="not valid!", target_base_endpoint="https://example.com/ws/"
        )

        with self.assertRaises(ValidationError):
            obj.create_gateway()

        mocked.return_value.create_api.assert_not_called()
        self.assertFalse(ApiGateway.objects.exists())

    def test_saving_named_fields_does_not_re_validate_the_whole_record(self):
        """Progress writes must not fail because an unrelated field is invalid."""
        obj = self._gateway()
        obj.api_name = "not valid!"

        obj.save(update_fields=["last_error", "updated_on"])  # no ValidationError

        with self.assertRaises(ValidationError):
            obj.save()

    def test_records_created_by_hand_are_left_alone(self):
        """Registering an existing API by hand must not trigger provisioning."""
        obj = self._gateway(api_id="existing", api_created=True)

        with patch("django_aws_api_gateway_websockets.models.get_boto3_client") as aws:
            self.assertIs(False, obj.create_gateway())

        aws.assert_not_called()


class ApiGatewayAdditionalRouteDeployedStateTestCase(TestCase):
    """An additional route is marked ``deployed`` once it exists in AWS, so a later save
    does not create it a second time."""

    def _client(self):
        client = MagicMock()
        client.create_api.return_value = {"ApiId": "A1", "ApiEndpoint": "wss://x"}
        client.create_integration.return_value = {"IntegrationId": "i1"}
        client.create_deployment.return_value = {"DeploymentId": "d1"}
        client.get_routes.return_value = {"Items": []}
        return client

    def _gateway(self, **kwargs):
        defaults = {
            "api_name": "Route Gateway",
            "target_base_endpoint": "https://example.com/ws/",
        }
        defaults.update(kwargs)
        return ApiGateway.objects.create(**defaults)

    def _route(self, gateway, key="report", **kwargs):
        return ApiGatewayAdditionalRoute.objects.create(
            api_gateway=gateway,
            name=f"Route {key}",
            route_key=key,
            integration_url=f"https://example.com/ws/{key}",
            **kwargs,
        )

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_create_gateway_marks_its_additional_routes_deployed(self, mocked):
        mocked.return_value = self._client()
        gateway = self._gateway()
        first = self._route(gateway, "report")
        second = self._route(gateway, "export")

        gateway.create_gateway()

        for route in (first, second):
            route.refresh_from_db()
            self.assertTrue(route.deployed, route.route_key)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_editing_a_route_after_create_gateway_does_not_create_it_again(
        self, mocked
    ):
        """The bug: the route was never marked deployed, so any later save re-created it."""
        client = mocked.return_value = self._client()
        gateway = self._gateway()
        route = self._route(gateway, "report")
        gateway.create_gateway()
        calls_after_creation = client.create_integration.call_count
        route.refresh_from_db()
        route.api_gateway.refresh_from_db()  # the gateway now has a deployment ID

        route.name = "Renamed"
        route.save()

        self.assertEqual(calls_after_creation, client.create_integration.call_count)
        route.refresh_from_db()
        self.assertEqual("Renamed", route.name)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_route_that_already_exists_in_aws_is_marked_deployed_when_resuming(
        self, mocked
    ):
        client = mocked.return_value = self._client()
        client.get_routes.return_value = {"Items": [{"RouteKey": "report"}]}
        gateway = self._gateway(
            api_id="A1",
            api_created=True,
            provisioning_status=ApiGateway.ProvisioningStatus.API_CREATED,
        )
        route = self._route(gateway, "report")

        gateway.create_gateway()

        route.refresh_from_db()
        self.assertTrue(route.deployed)
        created = [
            c.kwargs["IntegrationUri"] for c in client.create_integration.call_args_list
        ]
        self.assertNotIn("https://example.com/ws/report", created)

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_a_new_route_on_a_deployed_gateway_is_deployed_and_the_deployment_id_kept(
        self, mocked
    ):
        client = mocked.return_value = self._client()
        client.create_deployment.return_value = {"DeploymentId": "d-new"}
        gateway = self._gateway(api_id="A1", deployment_id="d-old")

        route = self._route(gateway, "report")

        route.refresh_from_db()
        gateway.refresh_from_db()
        self.assertTrue(route.deployed)
        self.assertEqual("d-new", gateway.deployment_id)  # saved, not only in memory

    @patch("django_aws_api_gateway_websockets.models.get_boto3_client")
    def test_saving_that_route_again_does_not_call_aws(self, mocked):
        client = mocked.return_value = self._client()
        gateway = self._gateway(api_id="A1", deployment_id="d-old")
        route = self._route(gateway, "report")
        route.refresh_from_db()
        calls = client.create_integration.call_count
        clients = mocked.call_count

        route.name = "Renamed"
        route.save()

        self.assertEqual(calls, client.create_integration.call_count)
        self.assertEqual(clients, mocked.call_count)

    def test_create_route_marks_deployed_without_saving_through_save(self):
        """create_route must not call save(), which could create the route again."""
        client = self._client()
        gateway = self._gateway(api_id="A1", deployment_id="")
        route = self._route(gateway, "report")

        with patch.object(ApiGatewayAdditionalRoute, "save") as mocked_save:
            route.create_route(client, deploy=False)

        mocked_save.assert_not_called()
        route.refresh_from_db()
        self.assertTrue(route.deployed)
        client.create_deployment.assert_not_called()

    def test_create_route_refreshes_updated_on(self):
        client = self._client()
        gateway = self._gateway(api_id="A1", deployment_id="")
        route = self._route(gateway, "report")
        before = ApiGatewayAdditionalRoute.objects.get(pk=route.pk).updated_on

        route.create_route(client, deploy=False)

        self.assertGreater(
            ApiGatewayAdditionalRoute.objects.get(pk=route.pk).updated_on, before
        )

    def test_a_route_that_is_not_saved_yet_is_marked_in_memory_only(self):
        route = ApiGatewayAdditionalRoute(
            api_gateway=ApiGateway(api_id="A1"),
            route_key="report",
            integration_url="https://example.com/ws/report",
        )

        route.create_route(self._client(), deploy=False)

        self.assertTrue(route.deployed)


def _deployed_gateway(**kwargs):
    values = {
        "api_name": "gw",
        "target_base_endpoint": "https://www.example.com/ws/",
        "api_id": "api1",
        "api_created": True,
        "deployment_id": "d1",
    }
    values.update(kwargs)
    return ApiGateway.objects.create(**values)


@patch("django_aws_api_gateway_websockets.models.get_boto3_client")
class ApiGatewaySaveSyncsToAwsTestCase(RunsAwsCallsAtOnceMixin, TestCase):
    """Saving a deployed gateway pushes the changed fields to AWS"""

    def setUp(self):
        super().setUp()
        self.gateway = _deployed_gateway()

    def reload(self):
        return ApiGateway.objects.get(pk=self.gateway.pk)

    def test_changing_the_description_updates_the_api_and_deploys(self, mocked_client):
        client = mocked_client.return_value
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        gateway = self.reload()
        gateway.api_description = "New"

        gateway.save()

        client.update_api.assert_called_once_with(ApiId="api1", Description="New")
        self.assertEqual("d2", self.reload().deployment_id)

    def test_changing_the_base_url_repoints_the_default_routes(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = {
            "Items": [
                {"RouteId": "r1", "RouteKey": "$connect", "Target": "integrations/i1"}
            ]
        }
        client.get_integrations.return_value = {"Items": []}
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        gateway = self.reload()
        gateway.target_base_endpoint = "https://new.example.com/ws"

        gateway.save()

        client.update_integration.assert_called_once_with(
            ApiId="api1",
            IntegrationId="i1",
            IntegrationUri="https://new.example.com/ws/connect",
        )

    def test_a_save_that_changes_nothing_does_not_call_aws(self, mocked_client):
        self.reload().save()
        mocked_client.assert_not_called()

    def test_saving_twice_pushes_a_change_once(self, mocked_client):
        mocked_client.return_value.create_deployment.return_value = {
            "DeploymentId": "d2"
        }
        gateway = self.reload()
        gateway.api_description = "New"
        gateway.save()
        gateway.save()
        self.assertEqual(1, mocked_client.return_value.update_api.call_count)

    def test_a_gateway_that_is_not_deployed_is_not_pushed(self, mocked_client):
        ApiGateway.objects.filter(pk=self.gateway.pk).update(deployment_id="")
        gateway = self.reload()
        gateway.api_description = "New"
        gateway.save()
        mocked_client.assert_not_called()

    def test_push_to_aws_false_saves_without_calling_aws(self, mocked_client):
        gateway = self.reload()
        gateway.api_description = "New"
        gateway.save(push_to_aws=False)
        mocked_client.assert_not_called()
        self.assertEqual("New", self.reload().api_description)

    def test_update_fields_saves_never_call_aws(self, mocked_client):
        gateway = self.reload()
        gateway.api_description = "New"
        gateway.save(update_fields=["api_description"])
        mocked_client.assert_not_called()

    def test_a_new_gateway_is_not_pushed(self, mocked_client):
        _deployed_gateway(api_name="other")
        mocked_client.assert_not_called()

    def test_an_aws_failure_keeps_the_local_change_and_raises(self, mocked_client):
        mocked_client.return_value.update_api.side_effect = ClientError(
            {"Error": {"Code": "BadRequestException"}}, "UpdateApi"
        )
        gateway = self.reload()
        gateway.api_description = "New"

        with self.assertRaisesMessage(ApiGatewaySyncError, "BadRequestException"):
            gateway.save()

        gateway = self.reload()
        self.assertEqual("New", gateway.api_description)
        self.assertEqual("ClientError: BadRequestException", gateway.last_error)


@patch("django_aws_api_gateway_websockets.models.get_boto3_client")
class AdditionalRouteSyncsToAwsTestCase(RunsAwsCallsAtOnceMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.gateway = _deployed_gateway()
        self.route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://www.example.com/ws/chat",
            deployed=True,
            route_id="r1",
            integration_id="i1",
        )

    def remote(self, key="chat"):
        return {
            "Items": [{"RouteId": "r1", "RouteKey": key, "Target": "integrations/i1"}]
        }

    def test_changing_the_integration_url_updates_the_integration(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = self.remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.integration_url = "https://www.example.com/ws/new"

        route.save()

        client.update_integration.assert_called_once_with(
            ApiId="api1",
            IntegrationId="i1",
            IntegrationUri="https://www.example.com/ws/new",
        )
        client.update_route.assert_not_called()
        client.create_deployment.assert_called_once()
        self.assertEqual("d2", ApiGateway.objects.get(pk=self.gateway.pk).deployment_id)

    def test_changing_the_route_key_renames_the_route(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = self.remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.route_key = "chat2"

        route.save()

        client.update_route.assert_called_once_with(
            ApiId="api1", RouteId="r1", RouteKey="chat2"
        )

    def test_an_unchanged_save_does_not_call_aws(self, mocked_client):
        ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk).save()
        mocked_client.assert_not_called()

    def test_changing_the_name_does_not_call_aws(self, mocked_client):
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.name = "Renamed"
        route.save()
        mocked_client.assert_not_called()

    def test_a_route_missing_in_aws_is_created_on_update(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = {"Items": []}
        client.create_integration.return_value = {"IntegrationId": "i9"}
        client.create_route.return_value = {"RouteId": "r9"}
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.integration_url = "https://www.example.com/ws/new"

        route.save()

        client.create_route.assert_called_once()
        route.refresh_from_db()
        self.assertEqual("r9", route.route_id)

    def test_push_to_aws_false_saves_without_calling_aws(self, mocked_client):
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.integration_url = "https://www.example.com/ws/new"
        route.save(push_to_aws=False)
        mocked_client.assert_not_called()

    def test_an_aws_failure_keeps_the_local_change_and_raises(self, mocked_client):
        mocked_client.return_value.get_routes.side_effect = BotoCoreError()
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.integration_url = "https://www.example.com/ws/new"

        with self.assertRaises(ApiGatewaySyncError):
            route.save()

        route.refresh_from_db()
        self.assertEqual("https://www.example.com/ws/new", route.integration_url)

    def test_deleting_a_route_removes_it_from_aws_and_deploys(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = self.remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        self.route.delete()

        client.delete_route.assert_called_once_with(ApiId="api1", RouteId="r1")
        client.delete_integration.assert_called_once_with(
            ApiId="api1", IntegrationId="i1"
        )
        client.create_deployment.assert_called_once()
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    def test_a_route_already_gone_from_aws_is_deleted_locally(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = {"Items": []}
        self.route.delete()
        client.delete_route.assert_not_called()
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    def test_aws_not_found_on_delete_is_ignored(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = self.remote()
        client.delete_route.side_effect = ClientError(
            {"Error": {"Code": "NotFoundException"}}, "DeleteRoute"
        )
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        self.route.delete()
        client.delete_integration.assert_called_once()

    def test_an_aws_failure_on_delete_keeps_the_route(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = self.remote()
        client.delete_route.side_effect = ClientError(
            {"Error": {"Code": "BadRequestException"}}, "DeleteRoute"
        )
        with self.assertRaises(ApiGatewaySyncError):
            self.route.delete()
        self.assertTrue(ApiGatewayAdditionalRoute.objects.exists())

    def test_a_route_not_deployed_is_deleted_without_calling_aws(self, mocked_client):
        ApiGatewayAdditionalRoute.objects.filter(pk=self.route.pk).update(
            deployed=False
        )
        ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk).delete()
        mocked_client.assert_not_called()

    def test_deleting_the_gateway_does_not_change_aws(self, mocked_client):
        self.gateway.delete()
        mocked_client.assert_not_called()
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    def test_a_gateway_queryset_delete_does_not_change_aws(self, mocked_client):
        ApiGateway.objects.filter(pk=self.gateway.pk).delete()
        mocked_client.assert_not_called()
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    def test_a_cascade_from_another_model_does_not_change_aws(self, mocked_client):
        """A host model deleting the gateway sends its own object as the origin."""
        host = MagicMock()
        for route in ApiGatewayAdditionalRoute.objects.all():
            post_delete.send(
                sender=ApiGatewayAdditionalRoute, instance=route, origin=host
            )
        mocked_client.assert_not_called()

    def test_a_route_queryset_delete_removes_each_route_from_aws(self, mocked_client):
        client = mocked_client.return_value
        client.get_routes.return_value = self.remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        ApiGatewayAdditionalRoute.objects.filter(pk=self.route.pk).delete()

        client.delete_route.assert_called_once_with(ApiId="api1", RouteId="r1")
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    def test_creating_a_route_stores_the_aws_ids(self, mocked_client):
        client = mocked_client.return_value
        client.create_integration.return_value = {"IntegrationId": "i7"}
        client.create_route.return_value = {"RouteId": "r7"}
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.gateway,
            name="New",
            route_key="new",
            integration_url="https://www.example.com/ws/new",
        )

        route.refresh_from_db()
        self.assertEqual(
            ("r7", "i7", True), (route.route_id, route.integration_id, route.deployed)
        )


def _client_error(code="BadRequestException", operation="UpdateApi"):
    return ClientError({"Error": {"Code": code}}, operation)


@patch("django_aws_api_gateway_websockets.models.get_boto3_client")
class AwsCallsAfterCommitTestCase(TestCase):
    """Inside a transaction an AWS call waits for the commit, so it holds no locks."""

    def setUp(self):
        self.gateway = _deployed_gateway()
        self.route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://www.example.com/ws/chat",
            deployed=True,
            route_id="r1",
            integration_id="i1",
        )

    def _remote(self):
        return {
            "Items": [
                {"RouteId": "r1", "RouteKey": "chat", "Target": "integrations/i1"}
            ]
        }

    def _edited_gateway(self):
        gateway = ApiGateway.objects.get(pk=self.gateway.pk)
        gateway.api_description = "New"
        return gateway

    def test_a_gateway_save_calls_aws_only_when_the_transaction_commits(
        self, mocked_client
    ):
        client = mocked_client.return_value
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self._edited_gateway().save()
            client.update_api.assert_not_called()

        self.assertEqual(1, len(callbacks))
        self.assertEqual(
            "New", ApiGateway.objects.get(pk=self.gateway.pk).api_description
        )
        callbacks[0]()
        client.update_api.assert_called_once_with(ApiId="api1", Description="New")

    def test_a_rolled_back_save_never_calls_aws(self, mocked_client):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    self._edited_gateway().save()
                    raise RuntimeError("abort")

        self.assertEqual([], callbacks)
        mocked_client.assert_not_called()
        self.assertEqual("", ApiGateway.objects.get(pk=self.gateway.pk).api_description)

    def test_a_route_update_calls_aws_only_when_the_transaction_commits(
        self, mocked_client
    ):
        client = mocked_client.return_value
        client.get_routes.return_value = self._remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.integration_url = "https://www.example.com/ws/new"

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            route.save()
            client.get_routes.assert_not_called()

        callbacks[0]()
        client.update_integration.assert_called_once()

    def test_creating_a_route_still_calls_aws_at_once(self, mocked_client):
        client = mocked_client.return_value
        client.create_integration.return_value = {"IntegrationId": "i9"}
        client.create_route.return_value = {"RouteId": "r9"}
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.gateway,
            name="New",
            route_key="new",
            integration_url="https://www.example.com/ws/new",
        )

        client.create_route.assert_called_once()
        route.refresh_from_db()
        self.assertEqual("r9", route.route_id)

    def test_deleting_a_route_removes_it_in_aws_after_the_commit_once(
        self, mocked_client
    ):
        client = mocked_client.return_value
        client.get_routes.return_value = self._remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk).delete()
            client.delete_route.assert_not_called()
            self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

        self.assertEqual(1, len(callbacks))
        callbacks[0]()
        client.delete_route.assert_called_once_with(ApiId="api1", RouteId="r1")

    def test_a_queryset_delete_removes_each_route_in_aws_after_the_commit(
        self, mocked_client
    ):
        client = mocked_client.return_value
        client.get_routes.return_value = self._remote()
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            ApiGatewayAdditionalRoute.objects.filter(pk=self.route.pk).delete()
            client.delete_route.assert_not_called()

        for callback in callbacks:
            callback()
        client.delete_route.assert_called_once_with(ApiId="api1", RouteId="r1")

    def test_deleting_the_gateway_queues_nothing_for_its_routes(self, mocked_client):
        with self.captureOnCommitCallbacks(execute=True):
            ApiGateway.objects.filter(pk=self.gateway.pk).delete()

        mocked_client.assert_not_called()

    def test_a_failure_at_commit_keeps_the_local_change_and_is_raised(
        self, mocked_client
    ):
        mocked_client.return_value.update_api.side_effect = _client_error()

        with self.assertRaisesMessage(ApiGatewaySyncError, "BadRequestException"):
            with self.captureOnCommitCallbacks(execute=True):
                self._edited_gateway().save()

        gateway = ApiGateway.objects.get(pk=self.gateway.pk)
        self.assertEqual("New", gateway.api_description)
        self.assertEqual("ClientError: BadRequestException", gateway.last_error)

    def test_collected_failures_are_not_raised_and_every_call_runs(self, mocked_client):
        client = mocked_client.return_value
        client.update_api.side_effect = _client_error()
        client.get_routes.side_effect = BotoCoreError()
        route = ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)
        route.integration_url = "https://www.example.com/ws/new"

        with collect_deferred_sync_errors() as errors:
            with self.captureOnCommitCallbacks(execute=True):
                self._edited_gateway().save()
                route.save()

        self.assertEqual(2, len(errors))
        client.update_api.assert_called_once()
        client.get_routes.assert_called_once()

    def test_collecting_errors_outside_the_block_does_not_leak(self, mocked_client):
        with collect_deferred_sync_errors():
            pass
        mocked_client.return_value.update_api.side_effect = _client_error()

        with self.assertRaises(ApiGatewaySyncError):
            with self.captureOnCommitCallbacks(execute=True):
                self._edited_gateway().save()


@patch("django_aws_api_gateway_websockets.models.get_boto3_client")
class AwsCallsOutsideATransactionTestCase(TransactionTestCase):
    """With no transaction open the call runs at once, and its error reaches the caller."""

    def setUp(self):
        self.gateway = _deployed_gateway()
        self.route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://www.example.com/ws/chat",
            deployed=True,
            route_id="r1",
            integration_id="i1",
        )

    def test_a_gateway_save_calls_aws_at_once(self, mocked_client):
        client = mocked_client.return_value
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        gateway = ApiGateway.objects.get(pk=self.gateway.pk)
        gateway.api_description = "New"

        gateway.save()

        client.update_api.assert_called_once_with(ApiId="api1", Description="New")

    def test_a_failure_reaches_the_caller_and_keeps_the_change(self, mocked_client):
        mocked_client.return_value.update_api.side_effect = _client_error()
        gateway = ApiGateway.objects.get(pk=self.gateway.pk)
        gateway.api_description = "New"

        with self.assertRaises(ApiGatewaySyncError):
            gateway.save()

        self.assertEqual(
            "New", ApiGateway.objects.get(pk=self.gateway.pk).api_description
        )

    def test_a_route_delete_changes_aws_first_and_a_failure_keeps_the_route(
        self, mocked_client
    ):
        client = mocked_client.return_value
        client.get_routes.return_value = {
            "Items": [
                {"RouteId": "r1", "RouteKey": "chat", "Target": "integrations/i1"}
            ]
        }
        client.delete_route.side_effect = _client_error(
            "BadRequestException", "DeleteRoute"
        )

        with self.assertRaises(ApiGatewaySyncError):
            ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk).delete()

        self.assertTrue(ApiGatewayAdditionalRoute.objects.exists())


@patch("django_aws_api_gateway_websockets.models.get_boto3_client")
class PushChangesSettingTestCase(RunsAwsCallsAtOnceMixin, TestCase):
    """``WEBSOCKETS["push_changes_to_aws"]`` goes back to the behaviour before syncing existed.

    On by default. Off, an edit or delete changes only the local record, and a new route is
    still created in AWS when it is saved, as it always was.
    """

    def setUp(self):
        super().setUp()
        self.gateway = _deployed_gateway()
        self.route = ApiGatewayAdditionalRoute.objects.create(
            api_gateway=self.gateway,
            name="Chat",
            route_key="chat",
            integration_url="https://www.example.com/ws/chat",
            deployed=True,
            route_id="r1",
            integration_id="i1",
        )

    def _gateway(self):
        return ApiGateway.objects.get(pk=self.gateway.pk)

    def _route(self):
        return ApiGatewayAdditionalRoute.objects.get(pk=self.route.pk)

    def _new_route(self, key="report"):
        return ApiGatewayAdditionalRoute(
            api_gateway=self._gateway(),
            name=key,
            route_key=key,
            integration_url=f"https://www.example.com/ws/{key}",
        )

    def _safe(self, mocked_client):
        """Give the mock client real answers, so a wrong call fails a test and cannot loop.

        A bare MagicMock returns a truthy ``NextToken`` for ever, which would page for ever.
        """
        client = mocked_client.return_value
        client.get_routes.return_value = {"Items": []}
        client.get_integrations.return_value = {"Items": []}
        client.get_api.return_value = {}
        client.get_stage.return_value = {}
        client.get_deployment.return_value = {"Description": ""}
        client.create_deployment.return_value = {"DeploymentId": "d2"}
        client.create_integration.return_value = {"IntegrationId": "i9"}
        client.create_route.return_value = {"RouteId": "r9"}
        return client

    # on: the default

    def test_it_is_on_when_the_setting_is_absent(self, mocked_client):
        self._safe(mocked_client)
        with override_settings(WEBSOCKETS={}):
            gateway = self._gateway()
            gateway.api_description = "New"
            gateway.save()

        mocked_client.return_value.update_api.assert_called_once()

    @override_settings(WEBSOCKETS={"push_changes_to_aws": True})
    def test_it_is_on_when_set_to_true(self, mocked_client):
        self._safe(mocked_client)
        gateway = self._gateway()
        gateway.api_description = "New"
        gateway.save()

        mocked_client.return_value.update_api.assert_called_once()

    @override_settings(WEBSOCKETS={"push_changes_to_aws": "no"})
    def test_a_value_that_is_not_true_or_false_means_on(self, mocked_client):
        self._safe(mocked_client)
        gateway = self._gateway()
        gateway.api_description = "New"
        gateway.save()

        mocked_client.return_value.update_api.assert_called_once()

    # off

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_editing_a_gateway_changes_only_the_local_record(self, mocked_client):
        self._safe(mocked_client)
        gateway = self._gateway()
        gateway.api_description = "New"
        gateway.target_base_endpoint = "https://new.example.com/ws"

        gateway.save()

        mocked_client.assert_not_called()
        self.assertEqual("New", self._gateway().api_description)

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_editing_a_deployed_route_changes_only_the_local_record(
        self, mocked_client
    ):
        self._safe(mocked_client)
        route = self._route()
        route.integration_url = "https://www.example.com/ws/new"
        route.route_key = "chat2"

        route.save()

        mocked_client.assert_not_called()
        self.assertEqual("chat2", self._route().route_key)

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_deleting_a_route_does_not_call_aws(self, mocked_client):
        self._safe(mocked_client)
        self._route().delete()

        mocked_client.assert_not_called()
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_a_queryset_delete_does_not_call_aws(self, mocked_client):
        self._safe(mocked_client)
        ApiGatewayAdditionalRoute.objects.filter(pk=self.route.pk).delete()

        mocked_client.assert_not_called()
        self.assertFalse(ApiGatewayAdditionalRoute.objects.exists())

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_a_new_route_is_still_created_in_aws_when_saved(self, mocked_client):
        """Creating on save is the long-standing behaviour, so the setting does not remove it."""
        self._safe(mocked_client)
        client = mocked_client.return_value
        client.create_integration.return_value = {"IntegrationId": "i9"}
        client.create_route.return_value = {"RouteId": "r9"}
        client.create_deployment.return_value = {"DeploymentId": "d9"}
        route = self._new_route()

        route.save()

        client.create_route.assert_called_once()
        route.refresh_from_db()
        self.assertTrue(route.deployed)

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_a_failure_creating_a_route_raises_the_original_error(self, mocked_client):
        """As before syncing existed: callers that catch ClientError keep working."""
        self._safe(mocked_client)
        mocked_client.return_value.create_integration.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException"}}, "CreateIntegration"
        )

        with self.assertRaises(ClientError) as raised:
            self._new_route().save()

        self.assertNotIsInstance(raised.exception, ApiGatewaySyncError)

    @override_settings(WEBSOCKETS={"push_changes_to_aws": True})
    def test_when_on_a_failure_creating_a_route_raises_the_sync_error(
        self, mocked_client
    ):
        self._safe(mocked_client)
        mocked_client.return_value.create_integration.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException"}}, "CreateIntegration"
        )

        with self.assertRaises(ApiGatewaySyncError):
            self._new_route().save()

    # the explicit actions and arguments

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_sync_to_aws_still_works_when_the_setting_is_off(self, mocked_client):
        self._safe(mocked_client)
        client = mocked_client.return_value
        client.get_api.return_value = {"Name": "x", "Description": "Old"}
        client.get_routes.return_value = {"Items": []}
        client.get_integrations.return_value = {"Items": []}
        client.get_stage.return_value = {}
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        changes = self._gateway().sync_to_aws()

        self.assertTrue(changes)
        client.update_api.assert_called()

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_push_to_aws_true_overrides_the_setting_for_one_save(self, mocked_client):
        self._safe(mocked_client)
        gateway = self._gateway()
        gateway.api_description = "New"

        gateway.save(push_to_aws=True)

        mocked_client.return_value.update_api.assert_called_once()

    @override_settings(WEBSOCKETS={"push_changes_to_aws": True})
    def test_push_to_aws_false_overrides_the_setting_for_one_save(self, mocked_client):
        self._safe(mocked_client)
        gateway = self._gateway()
        gateway.api_description = "New"

        gateway.save(push_to_aws=False)

        mocked_client.assert_not_called()

    @override_settings(WEBSOCKETS={"push_changes_to_aws": False})
    def test_push_to_aws_true_overrides_the_setting_on_delete(self, mocked_client):
        self._safe(mocked_client)
        client = mocked_client.return_value
        client.get_routes.return_value = {
            "Items": [
                {"RouteId": "r1", "RouteKey": "chat", "Target": "integrations/i1"}
            ]
        }
        client.create_deployment.return_value = {"DeploymentId": "d2"}

        self._route().delete(push_to_aws=True)

        client.delete_route.assert_called_once()
