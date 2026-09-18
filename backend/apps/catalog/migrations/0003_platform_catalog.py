from django.db import migrations


def catalog(apps, schema_editor):
    platform = apps.get_model("catalog", "Platform")
    for slug, name in [("meta", "Meta"), ("tiktok", "TikTok"), ("youtube", "YouTube"), ("google_ads", "Google Ads"), ("snapchat", "Snapchat"), ("pinterest", "Pinterest"), ("linkedin", "LinkedIn"), ("other", "Other")]:
        platform.objects.get_or_create(slug=slug, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_initial")]
    operations = [migrations.RunPython(catalog, migrations.RunPython.noop)]
