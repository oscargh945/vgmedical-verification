from django.contrib.auth import authenticate
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        username = data.get("username")
        password = data.get("password")
        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if not user.is_active:
                    ms = "This account is disabled."
                    raise serializers.ValidationError(ms)
                data["user"] = user
            else:
                ms = "Unable to log in with the provided credentials."
                raise serializers.ValidationError(
                    ms,
                )
        else:
            ms = "It must include email and password."
            raise serializers.ValidationError(
                ms,
            )
        return data
