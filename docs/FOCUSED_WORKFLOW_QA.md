# Focused request, deliverable and file UX pass

## Sequence root cause

DRF generated a compound uniqueness validator for `(request, sequence)`. It required
`sequence` before the create handler could allocate it. The dedicated deliverable
serializer makes sequence read-only and delegates compound uniqueness to the existing
database constraint. The transaction locks the parent request and allocates max + 1.
Client-provided sequence values cannot change ordering on create or edit.

## Files changed in this pass

- Backend: `apps/requests_app/{models,serializers,services,assignments,tasks}.py`;
  `apps/common/{resources,serializers,views,labels}.py`;
  `apps/workspaces/policies.py`; `apps/audit/services.py` (request notification visibility).
- Frontend: `src/{App,RequestWorkflow,DeliverableTeam,CreativeFiles,components,i18n}.tsx`;
  `src/{api,arabic}.ts`; `src/styles.css`.
- Tests: `backend/tests/{test_requests,test_focused_workflow}.py`;
  `frontend/src/focused.test.tsx`; `frontend/e2e/focused.spec.ts`;
  existing Drive browser selector accepts repeated filenames while retaining identity assertions.

Earlier hardening work remains in the working tree; this list describes this focused pass.

## Migrations

- `requests_app/0003_requestdeliverable_hook_requestdeliverable_notes_and_more.py`:
  additive hook, script, notes and production assignment model with uniqueness constraints.
- `requests_app/0004_backfill_primary_editor_assignments.py`: repeatable backfill
  preserving existing primary editors. Existing request, creative and file history is retained.

Both migrations have been applied to the local database. No database reset was performed.

## Production assignments

Each deliverable has named people, responsibilities and notes. Managers can manage
the team; requesters can manage supporting responsibilities on their own requests.
Editor assignment still requires the existing editor-management permission and an
eligible editor/manager. One canonical primary editor is synchronized with the editor
assignment, including the old assign actions. Other responsibilities grant visibility,
not production or approval permissions. Duplicate person/responsibility pairs and
inactive, foreign-workspace or disallowed-brand people are rejected.

## Request visibility

Workspace and brand restrictions always apply. Managers/reviewers see all scoped
requests; superusers retain administrative access. Other members see requests they
created, own, or have any deliverable assignment on (including the canonical editor).
List and detail endpoints share this policy; unrelated direct reads return 404.
Deliverables, source materials, assignments and request activity are scoped accordingly.
My Tasks includes assigned deliverables without changing membership permissions.

## File history and version selection

The Files tab fetches all pages of files and versions for the creative and groups
files by version, showing version number, label, status, current marker, filename,
role, provider and metadata. Earlier masters remain visible after revision and approval.
Generic CreativeFile creation is disabled; domain uploads remain the creation path.
Version choices filter by creative, and the backend rejects mismatched relationships.
Existing file uniqueness and upload/review rules remain intact.

## Labels and form initialization

Central backend `display_label` and `relation_labels` fields supply user names,
titles, version labels and filenames while preserving UUID identity. Generic details
and relation selectors render these labels. Arabic translations cover the new UI.
Forms wait for schema fields before initializing defaults, fixing a race observed
when opening Add Deliverable immediately on mobile.

## Verification

Backend checks and migration drift checks passed. Complete pytest: **89 passed**.
Ruff passed. Frontend unit tests: **11 passed**. Typecheck, lint and build passed.
Complete Playwright browser suite: **10 passed (2.3 minutes)**, including desktop, Arabic mobile, file history, Drive fixture, revisions, performance, experiments and isolation. This is the baseline before the subsequent workflow-integrity/automatic-Drive pass.

## Limits

Live Google OAuth/provider calls were not reauthorized or exercised in this pass;
Drive coverage uses existing automated provider tests and the explicit browser fixture.
The build reports a non-blocking JavaScript chunk-size warning. Database locking
behavior under production-scale simultaneous writes was not load-tested.
