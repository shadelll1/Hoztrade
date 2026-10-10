"""Заголовки безопасности для страниц витрины (в боевом режиме).

CSP разрешает только свои скрипты, стили и картинки; карта в «Контактах» — iframe Яндекс Карт. Админка Django
не затрагивается: у неё свои встроенные скрипты.
"""
from django.conf import settings

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "frame-src https://yandex.ru",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "object-src 'none'",
])
PERMISSIONS = "camera=(), microphone=(), geolocation=(), payment=()"


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG or request.path.startswith("/admin/"):
            return response
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS)
        return response
