from django.db import models
from rest_framework import serializers

from apps.common.resources import HIDDEN, PROTECTED
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.policies import membership, require, scope, validate_scope


def serializer_for(model):
    fields = [f.name for f in model._meta.fields if f.name not in HIDDEN] + [
        f.name for f in model._meta.many_to_many
    ]
    read_only = list(PROTECTED & set(fields))

    class ScopedSerializer(serializers.ModelSerializer):
        class Meta:
            pass

        def to_representation(self, instance):
            from apps.common.labels import display_label
            from apps.workspaces.policies import visible_requests

            result = super().to_representation(instance)
            result["display_label"] = display_label(instance)
            labels = {}
            req = self.context.get("request")
            for field in instance._meta.fields:
                if (
                    field.is_relation
                    and field.name in result
                    and getattr(instance, field.attname, None)
                ):
                    related = getattr(instance, field.name)
                    if (
                        req
                        and related._meta.label == "requests_app.CreativeRequest"
                        and not visible_requests(req.user, instance.workspace_id)
                        .filter(pk=related.pk)
                        .exists()
                    ):
                        labels[field.name] = "Restricted request"
                    else:
                        labels[field.name] = display_label(related)
            for field in instance._meta.many_to_many:
                if field.name in result:
                    labels[field.name] = [
                        display_label(obj) for obj in getattr(instance, field.name).all()
                    ]
            result["relation_labels"] = labels
            if instance._meta.model_name == "requestdeliverable":
                from apps.creatives.models import Creative
                from apps.requests_app.services import valid_primary_editor

                result["editor_ready"] = valid_primary_editor(instance)
                result["existing_creative"] = str(
                    Creative.objects.filter(deliverable=instance)
                    .values_list("pk", flat=True)
                    .first()
                    or ""
                )
            if instance._meta.model_name == "creativefile":
                asset = instance.storage_object
                result["asset"] = {
                    name: getattr(asset, name)
                    for name in [
                        "filename",
                        "provider",
                        "mime_type",
                        "size",
                        "width",
                        "height",
                        "duration",
                        "active",
                        "external_id",
                    ]
                }
                from apps.storage.models import Upload

                upload = (
                    Upload.objects.filter(
                        storage_object=asset,
                        version_id=instance.version_id,
                        provider="google_drive",
                    )
                    .order_by("-created_at")
                    .first()
                )
                result["asset"]["drive_upload"] = (
                    {"status": upload.status} if upload else asset.metadata.get("drive_upload")
                )
            return result

        def get_fields(self):
            result = super().get_fields()
            if model._meta.model_name == "requestdeliverable" and "sequence" in result:
                result["sequence"].required = False
            req = self.context.get("request")
            workspace = self.context.get("workspace")
            if req and workspace:
                for name, field in result.items():
                    target = (
                        field.child_relation
                        if isinstance(field, serializers.ManyRelatedField)
                        else field
                    )
                    if getattr(target, "queryset", None) is None:
                        continue
                    related = target.queryset.model
                    if related._meta.label == "accounts.User":
                        target.queryset = related.objects.filter(
                            is_active=True,
                            id__in=WorkspaceMembership.objects.filter(
                                workspace_id=workspace, active=True
                            ).values("user_id"),
                        )
                    elif any(f.name == "workspace" for f in related._meta.fields):
                        target.queryset = scope(target.queryset, req.user, workspace)
            return result

        def validate(self, attrs):
            req = self.context["request"]
            workspace = self.context["workspace"]
            if model._meta.model_name == "requestdeliverableassignment":
                deliverable = attrs.get("deliverable", getattr(self.instance, "deliverable", None))
                if deliverable:
                    attrs["brand"] = deliverable.brand
            if model._meta.model_name == "creative":
                from apps.creatives.services import bind_deliverable

                attrs = bind_deliverable(attrs, self.instance)
            if model._meta.model_name == "requestdeliverable":
                parent = attrs.get("request", getattr(self.instance, "request", None))
                if parent:
                    attrs.setdefault("brand", parent.brand)
                    if attrs["brand"] != parent.brand:
                        raise serializers.ValidationError(
                            {"brand": "Deliverable must match the request brand."}
                        )
                    from apps.creatives.models import Creative

                    if (
                        not self.instance
                        and Creative.objects.filter(
                            request=parent, deliverable__isnull=True
                        ).exists()
                    ):
                        raise serializers.ValidationError(
                            {
                                "request": "This request already has direct creatives. Finish it before adding deliverables."
                            }
                        )
                if attrs.get("quantity", 1) < 1:
                    raise serializers.ValidationError({"quantity": "Must be at least one."})
            brand = attrs.get("brand", getattr(self.instance, "brand", None))
            if model._meta.model_name == "storageconnection" and attrs.get(
                "auto_upload_default", getattr(self.instance, "auto_upload_default", False)
            ):
                if (
                    not brand
                    or attrs.get("provider", getattr(self.instance, "provider", "google_drive"))
                    != "google_drive"
                ):
                    raise serializers.ValidationError(
                        {
                            "auto_upload_default": "Select a brand and Google Drive provider for the automatic destination."
                        }
                    )
                if (
                    model.objects.filter(
                        workspace_id=workspace, brand=brand, auto_upload_default=True
                    )
                    .exclude(pk=getattr(self.instance, "pk", None))
                    .exists()
                ):
                    raise serializers.ValidationError(
                        {
                            "auto_upload_default": "Another connection is already the automatic destination for this brand."
                        }
                    )
            for key in ["title", "name"]:
                if (
                    any(f.name == key for f in model._meta.fields)
                    and not str(attrs.get(key, getattr(self.instance, key, ""))).strip()
                ):
                    raise serializers.ValidationError({key: "This field is required."})
            if (
                model._meta.label
                in [
                    "catalog.Product",
                    "catalog.Campaign",
                    "requests_app.CreativeRequest",
                    "creatives.Creative",
                ]
                and not brand
            ):
                raise serializers.ValidationError({"brand": "Select a brand."})
            if model._meta.label == "catalog.Brand":
                member = membership(req.user, workspace)
                if member and member.brand_restricted:
                    raise serializers.ValidationError(
                        "An unrestricted manager must create or edit brands."
                    )
            if model._meta.label != "catalog.Brand":
                validate_scope(req.user, workspace, brand)
            for key in ["owner", "assigned_editor"]:
                if (
                    self.instance
                    and key in attrs
                    and attrs[key] != getattr(self.instance, key, None)
                ):
                    require(req.user, workspace, "assign_editors")
                if key in attrs and attrs[key] is not None:
                    if self.instance or attrs[key] != req.user:
                        require(req.user, workspace, "assign_editors")
                    from apps.requests_app.services import assert_editor
                    from apps.workspaces.models import Workspace

                    assert_editor(attrs[key], Workspace.objects.get(pk=workspace), brand)
            if (
                self.instance
                and model._meta.model_name == "contentindexentry"
                and "machine_text" in attrs
                and attrs["machine_text"] != self.instance.machine_text
            ):
                raise serializers.ValidationError(
                    {
                        "machine_text": "Preserve machine output; write corrections in corrected_text."
                    }
                )
            for name, value in attrs.items():
                values = value if isinstance(value, list) else [value]
                for obj in values:
                    if (
                        isinstance(obj, models.Model)
                        and hasattr(obj, "brand_id")
                        and obj.brand_id
                        and obj.brand_id != getattr(brand, "pk", None)
                    ):
                        raise serializers.ValidationError(
                            {name: "Related record must belong to the same brand."}
                        )
            if self.instance:
                if model._meta.model_name == "storageconnection":
                    from apps.storage.models import DriveFolderMapping, StorageObject

                    used = (
                        DriveFolderMapping.objects.filter(connection=self.instance).exists()
                        or StorageObject.objects.filter(connection=self.instance).exists()
                    )
                    if used:
                        for name in ["root_folder_id", "shared_drive_id", "provider"]:
                            if name in attrs and attrs[name] != getattr(self.instance, name):
                                raise serializers.ValidationError(
                                    {
                                        name: "This connection has managed files. Create a new connection to change its storage boundary."
                                    }
                                )
                if model._meta.model_name == "deployment":
                    from apps.performance.models import PerformanceSnapshot

                    locked = (
                        self.instance.ad_id
                        or PerformanceSnapshot.objects.filter(deployment=self.instance).exists()
                    )
                    if locked:
                        for name in [
                            "provider",
                            "external_account_id",
                            "campaign_id",
                            "adset_id",
                            "ad_id",
                            "connection",
                        ]:
                            if name in attrs and attrs[name] != getattr(self.instance, name):
                                raise serializers.ValidationError(
                                    {
                                        name: "Deployment identity is locked. Create a corrected deployment to preserve history."
                                    }
                                )
                for name in [
                    "brand",
                    "creative",
                    "version",
                    "request",
                    "deliverable",
                    "experiment",
                    "deployment",
                    "source",
                    "parent",
                    "child",
                    "connection",
                ]:
                    if name in attrs and attrs[name] != getattr(self.instance, name):
                        raise serializers.ValidationError(
                            {name: "Historical relationships cannot be changed."}
                        )

            def value(key):
                return attrs.get(key, getattr(self.instance, key, None))

            creative, version = value("creative"), value("version")
            if creative and version and version.creative_id != creative.pk:
                raise serializers.ValidationError(
                    {"version": "Version belongs to a different creative."}
                )
            deliverable, request = value("deliverable"), value("request")
            if (
                deliverable
                and any(f.name == "request" for f in model._meta.fields)
                and (not request or deliverable.request_id != request.pk)
            ):
                raise serializers.ValidationError(
                    {"deliverable": "Deliverable must belong to the selected request."}
                )
            if model._meta.model_name == "deployment" and (
                not version or version.status not in ["approved", "published"]
            ):
                raise serializers.ValidationError(
                    {"version": "Deployments require an approved version."}
                )
            if model._meta.model_name == "creativefile":
                if not version or version.status != "draft":
                    raise serializers.ValidationError(
                        "Files can only be attached to a draft version."
                    )
                from apps.creatives.services import editor_access

                editor_access(req.user, creative)
                if (
                    attrs.get("role") == "master"
                    and model.objects.filter(version=version, role="master", active=True)
                    .exclude(pk=getattr(self.instance, "pk", None))
                    .exists()
                ):
                    raise serializers.ValidationError(
                        "This version already has a master. Create a new version for a replacement."
                    )
            if model._meta.model_name == "experimentarm":
                if value("experiment").status != "draft":
                    raise serializers.ValidationError("Experiment arms are frozen after starting.")
                dep = value("deployment")
                if dep and (
                    dep.creative_id != creative.pk or (version and dep.version_id != version.pk)
                ):
                    raise serializers.ValidationError("Deployment does not match the arm.")
            if (
                model._meta.model_name == "contextcreativelink"
                and value("document_version").status != "approved"
            ):
                raise serializers.ValidationError("Only approved context can be used as evidence.")
            if model._meta.model_name == "automationrule":
                conditions = value("conditions") or {}
                if not isinstance(conditions, dict) or any(
                    k not in ["creative_type", "outcome", "status"] or not isinstance(v, str)
                    for k, v in conditions.items()
                ):
                    raise serializers.ValidationError(
                        {
                            "conditions": "Use only creative_type, outcome and status string comparisons."
                        }
                    )
            if model._meta.model_name == "performancesnapshot":
                if value("interval_end") <= value("interval_start"):
                    raise serializers.ValidationError("End must follow start.")
                for key in ["spend", "revenue"]:
                    if (value(key) or 0) < 0:
                        raise serializers.ValidationError({key: "Must be nonnegative."})
            if model._meta.model_name == "clip" and (
                value("end") <= value("start") or value("start") < 0
            ):
                raise serializers.ValidationError("Clip end must follow a nonnegative start.")
            if model._meta.model_name == "creativerelationship":
                parent, child = value("parent"), value("child")
                if parent == child:
                    raise serializers.ValidationError("A creative cannot be its own parent.")
                seen = set()
                frontier = [child.pk]
                while frontier:
                    node = frontier.pop()
                    if node == parent.pk:
                        raise serializers.ValidationError("Lineage cannot contain cycles.")
                    if node in seen:
                        continue
                    seen.add(node)
                    frontier.extend(
                        model.objects.filter(parent_id=node).values_list("child_id", flat=True)
                    )
            return attrs

    ScopedSerializer.Meta.model = model
    ScopedSerializer.Meta.fields = fields
    ScopedSerializer.Meta.read_only_fields = read_only
    # RequestDeliverable.sequence is allocated by ScopedViewSet.perform_create().
    # DRF otherwise generates a UniqueTogetherValidator for (request, sequence)
    # and rejects the request *before* perform_create can allocate the sequence.
    # Keep the database UniqueConstraint as the integrity boundary and remove the
    # inappropriate client-side validator for this server-managed field.
    if model._meta.model_name in ["requestdeliverable", "storageconnection"]:
        ScopedSerializer.Meta.validators = []
    return ScopedSerializer
