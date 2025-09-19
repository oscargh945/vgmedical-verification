from allauth.account.adapter import get_adapter
from django.contrib.auth import get_user_model
from rest_framework import serializers

from vgmedical_verification.users.api.serializers.user import UserSerializer

User = get_user_model()


class RegisterSerializer(UserSerializer):
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            *UserSerializer.Meta.fields,
            "password1",
            "password2",
        )

    def validate(self, data):
        if not data.get("email"):
            ms = "Email is required."
            raise serializers.ValidationError(ms)
        if data["password1"] != data["password2"]:
            ms = "Passwords must match."
            raise serializers.ValidationError(ms)
        data["password"] = data["password1"]
        data.pop("password1")
        data.pop("password2")
        return data

    @staticmethod
    def validate_password1(password):
        return get_adapter().clean_password(password)

    @staticmethod
    def validate_email(email):
        if email:
            email = email.lower()
            email = get_adapter().clean_email(email)
            if User.objects.filter(email=email).exists():
                ms = "A user is already registered with this e-mail address."
                raise serializers.ValidationError(
                    ms,
                )
        return email

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create(**validated_data)
        user.set_password(password)
        user.save()
        return user
