from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalog"
    verbose_name = "Каталог"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import Category, Product
        from .tree import invalidate_tree

        # Правка группы или товара в админке меняет меню и счётчики — дерево перестроится при следующем запросе.
        for model in (Category, Product):
            post_save.connect(lambda **kw: invalidate_tree(), sender=model, weak=False,
                              dispatch_uid=f"tree-save-{model.__name__}")
            post_delete.connect(lambda **kw: invalidate_tree(), sender=model, weak=False,
                                dispatch_uid=f"tree-delete-{model.__name__}")
