from dj_rest_auth.views import LoginView
from django.conf import settings
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from vgmedical_verification.users.api.views.register import RegisterUserViewSet
from vgmedical_verification.users.api.views.user import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)


app_name = "api"
urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/register/", RegisterUserViewSet.as_view(), name="register"),
    path("document_processor/", include("vgmedical_verification.apps.document_processor.api.urls", namespace="document_processor")),
    *router.urls,
]
