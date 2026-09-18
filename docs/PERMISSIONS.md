# Permissions

Platform administrators are Django superusers. Workspace roles are membership-based, not a global role column.

| Role | Main capabilities |
| --- | --- |
| Manager | All workspace permissions |
| Media buyer | Requests, analytics, deployments, publishing, outcomes, experiments, lineage |
| Editor | Assigned creative/version work, comments, source materials, clips/content |
| Reviewer | Review/approval, comments and context |
| Requester | Create/track requests, comments and source materials |
| Viewer | Read the scoped library and workflow records |

The exact granular permission names and defaults live in `backend/apps/workspaces/policies.py`. A membership can contain boolean permission overrides and an explicit set of allowed brands. A restricted member cannot read global/unbranded business records or records from an unlisted brand.

Querysets filter by verified workspace membership. Serializer relation fields use the same filter, and validation requires related records to share the target brand. An accessible experiment cannot bind an inaccessible creative. Storage connection secrets and resumable session URIs are excluded from API serialization.

Managers can add users through Administration. Reusing an email updates that workspace membership; it does not overwrite the user's password. New users receive a temporary password and a change-password reminder. Platform admins can deactivate users in Django Admin; business history is preserved. Restricted managers cannot expand workspace membership access. Changes are audited.

Frontend navigation is convenient permission hiding; backend checks remain authoritative. Some advanced restrictions/overrides currently require the membership API rather than a dedicated visual editor. API example:

```http
POST /api/v1/workspaces/{workspace-id}/members/
Content-Type: application/json
X-CSRFToken: {session-csrf}

{"email":"editor@example.com","role":"editor","active":true,"brand_restricted":true,"brands":["brand-uuid"],"permission_overrides":{"manage_clips":false}}
```

The browser must already have an authenticated manager session. Never put credentials in URLs.
