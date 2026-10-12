from django.db import migrations

PERMISSIONS = {"use_crm": "Работа в CRM", "view_reports": "Отчёты CRM"}
GROUPS = {
    "Менеджеры": ["use_crm"],
    "Руководители": ["use_crm", "view_reports"],
}


def create_groups(apps, schema_editor):
    """Группы доступа к CRM. Сотрудника добавляют в группу в админке: Пользователи → Группы.

    Права создаются здесь же: обычно Django заводит их после всех миграций, а группе они нужны сейчас.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ct, _ = ContentType.objects.get_or_create(app_label="crm", model="deal")
    perms = {code: Permission.objects.get_or_create(content_type=ct, codename=code, defaults={"name": name})[0]
             for code, name in PERMISSIONS.items()}
    for name, codenames in GROUPS.items():
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.add(*(perms[c] for c in codenames))


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_groups, migrations.RunPython.noop)]
