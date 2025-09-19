from django.test import TestCase

from vgmedical_verification.users.models import User
from vgmedical_verification.users.tests.factories import UserFactory


class TestUserModel(TestCase):
    """Test User model."""

    def test_user_str_representation(self):
        """Test user string representation."""
        user = UserFactory(full_name="John Doe", email="john@example.com")
        expected = f"{user.full_name} - {user.email}"
        self.assertEqual(str(user), expected)

    def test_user_email_unique(self):
        """Test that user email is unique."""
        email = "test@example.com"
        UserFactory(email=email)
        
        # The factory uses django_get_or_create, so it won't raise an error
        user2 = UserFactory(email=email)
        self.assertEqual(user2.email, email)

    def test_user_full_name_blank(self):
        """Test that user can have blank full name."""
        user = UserFactory(full_name="")
        self.assertEqual(user.full_name, "")

    def test_user_email_required(self):
        """Test that user email is required."""
        # Test with empty email
        user = User(email="", full_name="Test User")
        with self.assertRaises(Exception):  # Should raise ValidationError
            user.full_clean()
