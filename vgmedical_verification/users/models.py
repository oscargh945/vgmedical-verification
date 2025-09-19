import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.db.models import EmailField
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    # First and last name do not cover full_name patterns around the globe
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = CharField(_("Full Name of User"), blank=True, max_length=255)
    email = EmailField(_("email address"), unique=True)

    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    username = None  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def __str__(self):
        return f"{self.full_name} - {self.email}"
