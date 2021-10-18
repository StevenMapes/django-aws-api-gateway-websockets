from django_aws_api_gateway_websockets import views
from django.test import override_settings, TestCase


class WebSocketViewTestCase(TestCase):

    def test_simple(self):
        self.assertTrue(True)

    def test_as_view(self):
        try:
            views.WebSocketView.as_view()
        except Exception as e:
            print(e)
            raise e

