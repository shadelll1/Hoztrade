from django.utils.functional import SimpleLazyObject

from .models import is_wholesale


def account(request):
    """Видит ли покупатель оптовые цены — для карточек товара. Запрос к профилю только при обращении."""
    return {"is_wholesale": SimpleLazyObject(lambda: is_wholesale(request.user))}
