from django.db import migrations


def promote_superusers(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Group = apps.get_model("auth", "Group")
    database = schema_editor.connection.alias
    users = User.objects.using(database).filter(is_superuser=True)
    users.update(role="admin")
    group, _ = Group.objects.using(database).get_or_create(name="Admin")
    through = User.groups.through
    through.objects.using(database).bulk_create(
        [through(user_id=user_id, group_id=group.pk) for user_id in users.values_list("pk", flat=True)],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(promote_superusers, migrations.RunPython.noop)]
