from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .tree import build_tree


def shop(request):
    """Данные компании и дерево каталога для шапки, меню и подвала."""
    return {
        "site": settings.SITE_INFO,
        "catalog_tree": SimpleLazyObject(build_tree),
    }
