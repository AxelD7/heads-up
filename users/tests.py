from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthTests(TestCase):
    """Tests for the log in, sign up and log out pages."""

    def setUp(self):
        self.password = "S3cure-pass-123"
        self.user = get_user_model().objects.create_user(
            username="jacob",
            email="jacob@example.com",
            password=self.password,
            phone_number="555-0100",
        )

    def test_empty_path_redirects_to_login_when_logged_out(self):
        response = self.client.get("/")
        self.assertRedirects(response, "/login/?next=/")

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    def test_login_with_username(self):
        response = self.client.post(reverse("login"), {"username": "jacob", "password": self.password})
        self.assertRedirects(response, reverse("events:event_list"))

    def test_login_with_email(self):
        response = self.client.post(reverse("login"), {"username": "JACOB@example.com", "password": self.password})
        self.assertRedirects(response, reverse("events:event_list"))

    def test_login_wrong_password_shows_error(self):
        response = self.client.post(reverse("login"), {"username": "jacob", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_follows_next(self):
        response = self.client.post(
            reverse("login") + "?next=/create/",
            {"username": "jacob", "password": self.password, "next": "/create/"},
        )
        self.assertRedirects(response, reverse("events:event_create"))

    def test_logged_in_user_visiting_login_goes_to_dashboard(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("login")), reverse("events:event_list"))
        self.assertRedirects(self.client.get(reverse("signup")), reverse("events:event_list"))

    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse("signup"), {
            "username": "newuser",
            "first_name": "New",
            "last_name": "User",
            "email": "New@Example.com",
            "phone_number": "555-0101",
            "date_format": "M/D/Y",
            "time_format": "12h",
            "password1": "An0ther-good-pass",
            "password2": "An0ther-good-pass",
        })
        self.assertRedirects(response, reverse("events:event_list"))
        user = get_user_model().objects.get(username="newuser")
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password("An0ther-good-pass"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_rejects_duplicate_email(self):
        response = self.client.post(reverse("signup"), {
            "username": "someoneelse",
            "first_name": "A",
            "last_name": "B",
            "email": "jacob@example.com",
            "phone_number": "555-0102",
            "password1": "An0ther-good-pass",
            "password2": "An0ther-good-pass",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email already exists.")

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(reverse("signup"), {
            "username": "someoneelse",
            "first_name": "A",
            "last_name": "B",
            "email": "other@example.com",
            "phone_number": "555-0102",
            "password1": "An0ther-good-pass",
            "password2": "different-pass-1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="someoneelse").exists())

    def test_logout_returns_to_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertRedirects(self.client.get("/"), "/login/?next=/")


class AccountCreationTests(TestCase):
    """Tests for creating a new account on the sign up page."""

    def valid_data(self, **overrides):
        data = {
            "username": "newuser",
            "first_name": "New",
            "last_name": "User",
            "email": "new@example.com",
            "phone_number": "(555) 010-0199",
            "date_format": "D/M/Y",
            "time_format": "24h",
            "password1": "An0ther-good-pass",
            "password2": "An0ther-good-pass",
        }
        data.update(overrides)
        return data

    def test_signup_page_shows_all_fields(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        for name in ["username", "first_name", "last_name", "email", "phone_number",
                     "date_format", "time_format", "password1", "password2"]:
            self.assertContains(response, f'name="{name}"')

    def test_signup_saves_profile_fields(self):
        self.client.post(reverse("signup"), self.valid_data())
        user = get_user_model().objects.get(username="newuser")
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "User")
        self.assertEqual(user.phone_number, "(555) 010-0199")
        self.assertEqual(user.date_format, "D/M/Y")
        self.assertEqual(user.time_format, "24h")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_new_user_can_log_in_afterwards(self):
        self.client.post(reverse("signup"), self.valid_data())
        self.client.post(reverse("logout"))
        response = self.client.post(reverse("login"), {"username": "new@example.com", "password": "An0ther-good-pass"})
        self.assertRedirects(response, reverse("events:event_list"))

    def test_signup_rejects_username_differing_only_in_case(self):
        get_user_model().objects.create_user(username="newuser", email="a@example.com", password="x")
        response = self.client.post(reverse("signup"), self.valid_data(username="NewUser"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="NewUser").exists())

    def test_signup_rejects_duplicate_email_in_different_case(self):
        get_user_model().objects.create_user(username="other", email="new@example.com", password="x")
        response = self.client.post(reverse("signup"), self.valid_data(email="NEW@example.com"))
        self.assertContains(response, "An account with this email already exists.")

    def test_signup_rejects_bad_phone_numbers(self):
        for phone in ["call me", "555-01ab", "123", "1234567890123456"]:
            with self.subTest(phone=phone):
                response = self.client.post(reverse("signup"), self.valid_data(phone_number=phone))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(get_user_model().objects.filter(username="newuser").exists())

    def test_signup_accepts_international_phone_number(self):
        self.client.post(reverse("signup"), self.valid_data(phone_number="+44 20 7946 0958"))
        self.assertTrue(get_user_model().objects.filter(username="newuser").exists())

    def test_signup_rejects_weak_password(self):
        response = self.client.post(reverse("signup"), self.valid_data(password1="password", password2="password"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="newuser").exists())

    def test_signup_requires_every_field(self):
        response = self.client.post(reverse("signup"), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_user_model().objects.count(), 0)
        for name in ["username", "first_name", "last_name", "email", "phone_number", "password1", "password2"]:
            self.assertIn(name, response.context["form"].errors)
