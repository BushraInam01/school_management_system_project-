from django.test import TestCase
from django.urls import reverse
from .models import User
class AccessTests(TestCase):
    def test_login_page_is_available(self): self.assertEqual(self.client.get(reverse("login")).status_code,200)
    def test_unauthenticated_dashboard_redirects(self): self.assertEqual(self.client.get(reverse("dashboard:home")).status_code,302)
