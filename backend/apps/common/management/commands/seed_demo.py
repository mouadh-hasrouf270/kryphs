from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User, UserProfile
from apps.audit.services import record
from apps.catalog.models import Brand, Campaign, Platform, Product
from apps.context_hub.models import ContextDocument, ContextDocumentVersion
from apps.creatives.models import Creative, CreativeComment, CreativeRelationship, CreativeVersion
from apps.experiments.models import Experiment, ExperimentArm
from apps.performance.models import Deployment, PerformanceSnapshot
from apps.performance.services import normalized
from apps.requests_app.models import CreativeRequest, RequestDeliverable
from apps.workspaces.models import Workspace, WorkspaceMembership


class Command(BaseCommand):
    help = "Create explicitly fictional local demo data. Never creates provider connections."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding is disabled when DEBUG=False.")
        if Workspace.objects.filter(slug="studio-demo").exists():
            self.stdout.write("Demo workspace exists; left unchanged.")
            return
        users = {}
        for role in ["manager", "media_buyer", "editor", "reviewer", "requester", "viewer"]:
            user, created = User.objects.get_or_create(
                email=f"{role}@demo.local",
                defaults={"display_name": role.replace("_", " ").title()},
            )
            if created:
                user.set_password("CreativeDemo!2026")
                user.save()
            UserProfile.objects.get_or_create(user=user, defaults={"preferred_language": "ar"})
            users[role] = user
        admin, created = User.objects.get_or_create(
            email="admin@demo.local",
            defaults={"display_name": "Studio Admin", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("CreativeDemo!2026")
            admin.save()
        UserProfile.objects.get_or_create(user=admin)
        ws = Workspace.objects.create(
            name="Olive Studio",
            slug="studio-demo",
            description="Fictional local demo studio",
            created_by=admin,
        )
        for role, user in users.items():
            WorkspaceMembership.objects.create(workspace=ws, user=user, role=role)
        WorkspaceMembership.objects.create(workspace=ws, user=admin, role="manager")
        brand = Brand.objects.create(
            workspace=ws, name="Noura Essentials", slug="noura", metadata={"demo": True}
        )
        product = Product.objects.create(
            workspace=ws,
            brand=brand,
            name="Daily Ritual Collection",
            description="Fictional skincare product for demonstration only.",
        )
        campaign = Campaign.objects.create(
            workspace=ws,
            brand=brand,
            name="A slower kind of morning",
            description="Autumn launch campaign — demo",
        )
        platforms = {}
        for name, slug in [
            ("Meta", "meta"),
            ("TikTok", "tiktok"),
            ("YouTube", "youtube"),
            ("Google Ads", "google_ads"),
            ("Snapchat", "snapchat"),
            ("Pinterest", "pinterest"),
            ("LinkedIn", "linkedin"),
            ("Other", "other"),
        ]:
            platforms[slug] = Platform.objects.get_or_create(slug=slug, defaults={"name": name})[0]
        req = CreativeRequest.objects.create(
            workspace=ws,
            brand=brand,
            code="REQ-DEMO-001",
            title="Autumn launch · The daily ritual",
            objective="Introduce the collection through calm, human stories.",
            details="Build two vertical videos: one focused on the morning routine, one showing the texture and ingredients. Demo brief only.",
            requester=users["requester"],
            owner=users["editor"],
            product=product,
            campaign=campaign,
            status="in_production",
            priority="high",
            due_date=timezone.now() + timedelta(days=4),
        )
        req.platforms.add(platforms["meta"], platforms["tiktok"])
        deliverables = []
        for i, title in enumerate(
            ["Morning routine · 20 seconds", "A closer look · 15 seconds"], 1
        ):
            deliverables.append(
                RequestDeliverable.objects.create(
                    workspace=ws,
                    brand=brand,
                    request=req,
                    sequence=i,
                    title=title,
                    assigned_editor=users["editor"],
                    status="in_production",
                    platform=platforms["meta"],
                )
            )
        titles = [
            "The morning ritual",
            "Made for your everyday",
            "Small moments, real stories",
            "A closer look",
            "Good things take time",
            "Your routine, reimagined",
        ]
        statuses = [
            "approved",
            "in_production",
            "ready_for_review",
            "assigned",
            "changes_requested",
            "new",
        ]
        creatives = []
        for i, (title, status) in enumerate(zip(titles, statuses), 1):
            creative = Creative.objects.create(
                workspace=ws,
                brand=brand,
                code=f"CR-DEMO-{i:03}",
                title=title,
                description=[
                    "Soft light. Simple ingredients. A story worth slowing down for.",
                    "A fresh perspective on the things we do every day.",
                    "An honest look at the people behind the product.",
                ][i % 3],
                request=req if i < 3 else None,
                deliverable=deliverables[i - 1] if i < 3 else None,
                product=product,
                campaign=campaign,
                owner=users["editor"],
                creative_type="image" if i % 3 == 0 else "video",
                status=status,
                outcome="winner" if i == 1 else "",
            )
            creatives.append(creative)
            if status not in ["new", "assigned"]:
                version = CreativeVersion.objects.create(
                    workspace=ws,
                    brand=brand,
                    creative=creative,
                    version_number=1,
                    label="v001",
                    editor=users["editor"],
                    notes="Initial concept exploring a quieter, more human visual direction.",
                    status={
                        "approved": "approved",
                        "ready_for_review": "submitted",
                        "changes_requested": "changes_requested",
                    }.get(status, "draft"),
                    approved_at=timezone.now() if status == "approved" else None,
                )
                creative.current_version = version
                if status == "approved":
                    creative.approved_version = version
                creative.save()
            CreativeComment.objects.create(
                workspace=ws,
                brand=brand,
                creative=creative,
                author=users["manager"],
                text="Keep the message clear and let the product story breathe.",
            )
            record(users["editor"], creative, "created")
        CreativeRelationship.objects.create(
            workspace=ws,
            brand=brand,
            parent=creatives[0],
            child=creatives[1],
            relationship="variant",
            hypothesis="A product-first opening may improve the first three seconds.",
            author=users["manager"],
        )
        dep = Deployment.objects.create(
            workspace=ws,
            brand=brand,
            title="Morning ritual · manual observation",
            creative=creatives[0],
            version=creatives[0].approved_version,
            provider="manual",
            state="active",
            deployed_at=timezone.now(),
        )
        for i in range(2):
            values = {
                "spend": 120 + i * 20,
                "impressions": 12000 + i * 3000,
                "reach": 8000,
                "clicks": 420 + i * 50,
                "conversions": 24 + i * 4,
                "revenue": 720 + i * 120,
            }
            PerformanceSnapshot.objects.create(
                workspace=ws,
                brand=brand,
                deployment=dep,
                provider="manual",
                interval_start=timezone.now() - timedelta(days=4 - i),
                interval_end=timezone.now() - timedelta(days=3 - i),
                **values,
                metrics=normalized(values),
            )
        experiment = Experiment.objects.create(
            workspace=ws,
            brand=brand,
            title="The opening moment",
            hypothesis="Does a product-first opening improve CTR?",
            primary_kpi="ctr",
        )
        for i, c in enumerate(creatives[:2]):
            ExperimentArm.objects.create(
                workspace=ws,
                brand=brand,
                experiment=experiment,
                name="Control" if i == 0 else "Product-first hook",
                control=i == 0,
                creative=c,
                version=c.current_version,
            )
        doc = ContextDocument.objects.create(
            workspace=ws,
            brand=brand,
            title="Noura · Voice and visual direction",
            category="guidelines",
        )
        version = ContextDocumentVersion.objects.create(
            workspace=ws,
            brand=brand,
            document=doc,
            version_number=1,
            content="Calm, thoughtful and human. Use natural light, honest language and clear product details. Never make unsupported health claims. Fictional demo guidelines.",
            status="approved",
            author=users["manager"],
        )
        doc.current_version = version
        doc.save()
        record(users["requester"], req, "request_created")
        self.stdout.write(
            self.style.SUCCESS(
                "Demo created. Login: manager@demo.local / CreativeDemo!2026 (local demo only)."
            )
        )
