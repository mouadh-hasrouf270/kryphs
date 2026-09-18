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

        def get_fields(self):
            result = super().get_fields()
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
            brand = attrs.get("brand", getattr(self.instance, "brand", None))
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
            if deliverable and (not request or deliverable.request_id != request.pk):
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
    return ScopedSerializer
