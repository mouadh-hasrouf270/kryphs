from django.db import migrations


def backfill(apps, schema_editor):
    deliverable = apps.get_model("requests_app", "RequestDeliverable")
    assignment = apps.get_model("requests_app", "RequestDeliverableAssignment")
    for obj in deliverable.objects.exclude(assigned_editor_id=None).iterator():
        assignment.objects.get_or_create(
            deliverable_id=obj.pk,
            user_id=obj.assigned_editor_id,
            role="editor",
            defaults={"workspace_id": obj.workspace_id, "brand_id": obj.brand_id},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("requests_app", "0003_requestdeliverable_hook_requestdeliverable_notes_and_more")
    ]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
