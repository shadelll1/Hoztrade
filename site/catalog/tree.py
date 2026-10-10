"""Дерево каталога одним запросом — для меню, главной и боковой панели.

Дерево нужно на каждой странице (меню, подвал), а меняется только при обмене с 1С и правках в админке. Поэтому
оно строится один раз и хранится в памяти процесса до смены версии: версия лежит в кэше Django и меняется
при импорте каталога и сохранении групп и товаров (invalidate_tree).
"""
import uuid

from django.core.cache import cache
from django.db.models import Count, Q

from .models import Category


class Node:
    __slots__ = ("category", "children", "own_count", "count")

    def __init__(self, category):
        self.category = category
        self.children = []
        self.own_count = 0
        self.count = 0

    def __getattr__(self, name):
        return getattr(self.category, name)


def build_tree():
    """Корни каталога с вложенными узлами и количеством опубликованных товаров (включая вложенные)."""
    categories = Category.objects.filter(is_published=True).annotate(
        n=Count("products", filter=Q(products__is_published=True))
    )
    nodes = {c.pk: Node(c) for c in categories}
    for node in nodes.values():
        node.own_count = node.category.n

    roots = []
    for node in nodes.values():
        parent = nodes.get(node.category.parent_id)
        (parent.children if parent else roots).append(node)

    def total(node):
        node.children.sort(key=lambda n: (n.sort, n.name))
        node.count = node.own_count + sum(total(child) for child in node.children)
        return node.count

    for root in roots:
        total(root)
    roots.sort(key=lambda n: (n.sort, n.name))
    return [r for r in roots if r.count > 0]


def find_node(roots, pk):
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node.pk == pk:
            return node
        stack.extend(node.children)
    return None


VERSION_KEY = "catalog_tree_version"
_memo = {}


def cached_tree():
    """Дерево каталога из памяти процесса; перестраивается, когда сменилась версия."""
    version = cache.get_or_set(VERSION_KEY, lambda: uuid.uuid4().hex, None)
    if _memo.get("version") != version:
        roots = build_tree()
        roots_by_pk = {}
        for root in roots:
            stack = [root]
            while stack:
                node = stack.pop()
                roots_by_pk[node.pk] = root
                stack.extend(node.children)
        _memo.update(version=version, roots=roots, roots_by_pk=roots_by_pk)
    return _memo["roots"]


def root_for(category_id):
    """Корневой раздел опубликованной группы по её ID (None — группа скрыта или не найдена)."""
    cached_tree()
    return _memo["roots_by_pk"].get(category_id)


def invalidate_tree():
    cache.set(VERSION_KEY, uuid.uuid4().hex, None)
