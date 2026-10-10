"""API обмена с 1С. Контракт — docs/api.md."""
import hmac

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CatalogUploadSerializer
from .services import import_catalog

EXCHANGE_CLIENT = "1c-exchange"


class ExchangeTokenAuthentication(BaseAuthentication):
    """Заголовок Authorization: Token <EXCHANGE_TOKEN> из site/.env."""

    def authenticate(self, request):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme != "Token":
            return None
        expected = settings.EXCHANGE_TOKEN
        if not expected or not hmac.compare_digest(token.strip(), expected):
            raise AuthenticationFailed("Неверный токен обмена.")
        return (None, EXCHANGE_CLIENT)

    def authenticate_header(self, request):
        # Наличие заголовка WWW-Authenticate переводит отказ в 401 вместо 403.
        return "Token"


class IsExchangeClient(BasePermission):
    message = "Нужен токен обмена: заголовок Authorization: Token <токен>."

    def has_permission(self, request, view):
        return request.auth == EXCHANGE_CLIENT


class ExchangeView(APIView):
    authentication_classes = [ExchangeTokenAuthentication]
    permission_classes = [IsExchangeClient]


class PingView(ExchangeView):
    def get(self, request):
        return Response({"status": "ok", "site": "Хозтрейд", "time": timezone.localtime().isoformat()})


class CatalogUploadView(ExchangeView):
    def post(self, request):
        serializer = CatalogUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response(import_catalog(serializer.validated_data))
