from rest_framework import serializers

from vgmedical_verification.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
        ]
