"""Explicit aggregate inputs; related choices retain the shared scope policy."""

from rest_framework import serializers

from apps.common.serializers import serializer_for
from apps.requests_app.models import (
    CreativeRequest,
    RequestDeliverable,
    RequestDeliverableAssignment,
)


class RequestDeliverableInputSerializer(serializer_for(RequestDeliverable)):
    title = serializers.CharField(max_length=200)
    quantity = serializers.IntegerField(min_value=1, max_value=1, default=1)

    class Meta:
        model = RequestDeliverable
        fields = [
            "title",
            "creative_type",
            "platform",
            "aspect_ratio",
            "quantity",
            "duration_target",
            "requirements",
            "hook",
            "script",
            "notes",
            "due_date",
            "assigned_editor",
            "brand",
        ]
        extra_kwargs = {"brand": {"write_only": True}}


BaseRequestDeliverableSerializer = serializer_for(RequestDeliverable)


class RequestDeliverableSerializer(BaseRequestDeliverableSerializer):
    """Public serializer for standalone deliverable create/edit.

    ``sequence`` is an ordering value owned by the server.  The database keeps
    the (request, sequence) unique constraint, while the API allocates the next
    value atomically in ``ResourceViewSet.perform_create``.  DRF's generated
    UniqueTogetherValidator would otherwise make ``sequence`` required before
    perform_create has a chance to allocate it.
    """

    sequence = serializers.IntegerField(read_only=True)
    quantity = serializers.IntegerField(min_value=1, max_value=1, default=1)

    class Meta(BaseRequestDeliverableSerializer.Meta):
        validators = []


class CreativeRequestCreateSerializer(serializer_for(CreativeRequest)):
    title = serializers.CharField(max_length=200)
    deliverables = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )

    class Meta:
        model = CreativeRequest
        fields = serializer_for(CreativeRequest).Meta.fields + ["deliverables"]
        read_only_fields = serializer_for(CreativeRequest).Meta.read_only_fields

    def validate(self, attrs):
        entries = attrs.pop("deliverables", None)
        attrs = super().validate(attrs)
        if entries is not None:
            if self.instance:
                raise serializers.ValidationError(
                    {"deliverables": "Edit existing deliverables separately."}
                )
            checked, errors = [], []
            for entry in entries:
                child = RequestDeliverableInputSerializer(
                    data={**entry, "brand": str(attrs["brand"].pk)}, context=self.context
                )
                valid = child.is_valid()
                errors.append({} if valid else child.errors)
                if valid:
                    checked.append({k: v for k, v in child.validated_data.items() if k != "brand"})
            if any(errors):
                raise serializers.ValidationError({"deliverables": errors})
            attrs["deliverables"] = checked
        return attrs


class CreativeRequestUpdateSerializer(CreativeRequestCreateSerializer):
    pass


BaseAssignmentSerializer = serializer_for(RequestDeliverableAssignment)


class RequestDeliverableAssignmentSerializer(BaseAssignmentSerializer):
    class Meta(BaseAssignmentSerializer.Meta):
        validators = []  # Checked atomically by the assignment service.
