# Security boundaries

- Sessions are HttpOnly, SameSite=Lax and Secure in production. Mutations, including login, require CSRF. No auth tokens in browser localStorage.
- Roles belong to active workspace memberships. Every public business queryset and submitted relationship is scoped. Restricted brands exclude unbranded records.
- Provider credentials and resumable URLs use Fernet authenticated encryption with `APP_ENCRYPTION_KEY`. General serializers/admin views omit them. Errors are sanitized.
- Uploads have an enforced size limit, sanitized names, random private paths and recognized binary signatures. Images are parsed/verified with Pillow. SVG/HTML uploads are rejected. Download is authorized and attachment-only. Antivirus and content moderation services are not bundled.
- Provider hosts are fixed in code; resumable session hosts are allow-listed. User destination URLs are validated and never fetched by this server. No arbitrary-code automations, eval or pickle deserialization.
- Publishing requires an approved version and exactly one active master. Provider success requires a confirmed response. Uncertain Meta steps are blocked from replay.
- Login/reset writes are rate-limited. Current throttle storage is process-local: use a shared cache or edge rate limiting before scaling web processes.
- Audit/history endpoints and operational admin records are read-only. Platform administrators and database operators remain trusted.
- Secrets are excluded from the clean ZIP, Docker build context and version control. Back up encryption keys separately; never paste keys into troubleshooting reports.

Production requires HTTPS, correct trusted proxy setup, explicit allowed hosts, DEBUG false, independently generated keys, off-host backup and a reviewed release checklist. Public API errors are presently English; UI locales do not change all server error strings.

Dependency audit snapshots are included as `dependency-audit-python.json` and `dependency-audit-npm.json`. They describe the audit time, not a permanent vulnerability guarantee. Re-run audits before deployment and during maintenance.
