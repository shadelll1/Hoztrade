"""API обмена с 1С. Контракт — docs/api.md."""
import hmac
import io

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.images import save_product_image
from catalog.models import Product
from delivery.serializers import DeliveryUploadSerializer
from delivery.services import import_delivery

from .models import ExchangeContact
from .serializers import CatalogUploadSerializer
from .services import import_catalog, remove_product_image

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
        ExchangeContact.objects.update_or_create(
            pk=1, defaults={"last_seen_at": timezone.now(), "last_path": request.path[:200]})
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


class DeliveryUploadView(ExchangeView):
    """Зоны доставки, автопарк и тарифы — полной посылкой."""

    def post(self, request):
        serializer = DeliveryUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response(import_delivery(serializer.validated_data))


MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


class ProductImageView(ExchangeView):
    """Фото товара из 1С: тело запроса — файл картинки, ?version= — версия из выгрузки каталога."""

    parser_classes = []  # тело читаем как есть, без разбора

    def put(self, request, ext_id):
        product = get_object_or_404(Product, ext_id=ext_id)
        version = request.query_params.get("version", "")[:100]
        data = request.body
        if not version or not data:
            return Response({"errors": "Нужны тело запроса (файл) и параметр version"},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(data) > MAX_IMAGE_BYTES:
            return Response({"errors": "Файл больше 5 МБ"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with Image.open(io.BytesIO(data)) as img:
                fmt = img.format
                img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            return Response({"errors": "Это не картинка"}, status=status.HTTP_400_BAD_REQUEST)
        if fmt not in IMAGE_FORMATS:
            return Response({"errors": f"Формат {fmt} не поддерживается"}, status=status.HTTP_400_BAD_REQUEST)

        save_product_image(product, data, version)
        return Response({"image": product.image.url, "thumb": product.thumb.url})

    def delete(self, request, ext_id):
        product = get_object_or_404(Product, ext_id=ext_id)
        remove_product_image(product)
        return Response(status=status.HTTP_204_NO_CONTENT)
