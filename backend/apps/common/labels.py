"""Read-only presentation labels. UUIDs remain API relationship identities."""


def display_label(obj):
    if obj is None:
        return ""
    kind = obj._meta.model_name
    if kind == "user":
        return obj.display_name or obj.email
    if kind == "creativeversion":
        number = f"v{obj.version_number:03}"
        suffix = f" — {obj.label}" if obj.label and obj.label != number else ""
        return f"{obj.creative.title} — {number}{suffix}"
    if kind == "creativefile":
        return f"{obj.storage_object.filename} · {obj.role} · {obj.version.label if obj.version_id else 'attachment'}"
    if kind == "requestdeliverableassignment":
        return f"{display_label(obj.user)} · {obj.role}"
    for name in ["title", "name", "filename", "label", "email", "action", "type"]:
        value = getattr(obj, name, None)
        if value:
            return str(value)
    return str(obj._meta.verbose_name)
