# CreativeManager — Standalone Django + React Platform
## MASTER CODEX BUILD SPECIFICATION / EXECUTION PROMPT

**Source reference:** `CreativeManager-v7.2.19-tested-youtube-resumable.zip`  
**Target:** a production-ready standalone Creative Operations platform built with Django + React + SQLite.  
**Primary language direction:** Arabic/RTL first, with English and French support.  
**Operating principle:** preserve the business behavior and useful features of the source module, fix its known defects, remove dependence on the old PHP Core Platform, and redesign the product as a clean standalone application with users, profiles, workspaces, roles, permissions, integrations, auditability, tests, documentation, and deployability.

---

# 0. EXECUTION INSTRUCTION TO CODEX

Read this entire specification before editing or generating code.

You are acting as the **senior staff software engineer, solution architect, security reviewer, QA engineer, DevOps engineer, and product engineer** for this project.

You are expected to use the full repository context and all available coding, search, inspection, test, lint, build, browser, terminal, and reasoning capabilities available to you.

Do not treat this as a quick prototype.

The requested output is a **working platform suitable for real internal company use**.

## Mandatory working behavior

1. Inspect the complete supplied reference ZIP before building.
2. Understand its workflows, schema, services, permissions, integrations, migrations, and UI behavior.
3. Do not blindly translate PHP into Python.
4. Rebuild the domain cleanly using Django/React while preserving valid business behavior.
5. Do not copy known defects from the reference implementation.
6. Build vertically usable functionality, not empty pages.
7. Run tests continuously.
8. Do not stop after scaffolding.
9. Do not stop for routine checkpoints or ask whether to continue.
10. Work through the milestones automatically until the requested platform is complete.
11. If a requirement is ambiguous, choose the safest maintainable production-quality interpretation and document the choice.
12. Preserve already-passing functionality whenever you modify an existing implementation.
13. Never fabricate success from an external provider.
14. Never create fake external IDs in production code.
15. Mocks/fakes must live only in explicitly named test/development providers.
16. A production provider without credentials, authorization, API capability, or a confirmed external response must fail clearly and safely.
17. Do not expose secrets, OAuth refresh tokens, access tokens, client secrets, passwords, or encryption keys in logs, API payloads, frontend state, or source control.
18. Deliver one coherent repository, not disconnected demos.
19. At completion, produce:
    - fully runnable source;
    - migrations;
    - seed/demo command;
    - tests;
    - `.env.example`;
    - local Windows instructions;
    - Docker production instructions;
    - backup/restore instructions;
    - Google integration setup guide;
    - deployment checklist;
    - architecture documentation;
    - final QA report;
    - known limitations report;
    - one clean standalone ZIP of the final project if your environment allows file packaging.

Do not report a feature as complete until its acceptance tests pass.

---

# 1. PROJECT GOAL

Rebuild the existing **CreativeManager** module as a fully standalone Creative Operations platform.

It must manage the complete creative lifecycle:

```text
Request
  → Deliverables
  → Assignment
  → Production
  → Creative
  → Creative Versions
  → Review / Feedback
  → Approval
  → File / Google Drive management
  → Deployment / Publishing
  → Performance
  → Winner / Loser / Fatigue decisions
  → Experiments
  → Variants / Refreshes / Lineage
  → Patterns / Evidence / Knowledge
  → Automation
```

This is not merely a file library and not merely a task manager.

The central business object is the **Creative** and its complete history.

---

# 2. IMPORTANT FINDINGS FROM THE REFERENCE MODULE

The reference module is a PHP module that depends on an external Core Platform. The new application must remove that dependency entirely.

The reference module contains approximately:

- 25 controllers
- 53 services
- 20 models
- 35 migrations
- 42 views
- Google Drive OAuth/sync/upload logic
- YouTube resumable upload
- advertising connections and performance sync
- Meta publishing workflow
- experiments
- automation
- creative lineage
- clips/content indexing
- context/knowledge management
- workspaces and brand access
- AR/FR/EN translations

The reference module should be treated as a **behavioral and domain reference**, not as code to port line-for-line.

## Known source defects that MUST NOT be migrated

At minimum, account for these verified problems while analyzing the legacy source:

- `Services/PublishingService.php` contains a PHP syntax error around destination URL validation.
- `Resources/views/library/evidence_assistant.php` contains a PHP control-flow syntax error.
- `Tools/import_legacy_csv.php` refers to a non-existent creative version status `in_review`.
- The same legacy importer has a SQL placeholder/value mismatch around `cm_creative_versions`.
- The legacy importer appears stale relative to workspace scoping.
- translation key `common.save` is used but missing.
- old documentation references tests that are not present in the supplied ZIP.
- old legacy JS/CSS files may remain but are not all active.

Do not reproduce these defects.

---

# 3. REQUIRED TECHNOLOGY STACK

## Backend

Use:

- Python 3.13 recommended.
- **Django 5.2 LTS**, using the latest released 5.2 security/patch version available at installation time.
- Django REST Framework.
- SQLite as the requested primary database for this release.
- Django ORM only for normal application access; no application feature should depend on raw SQLite-only SQL unless isolated behind a documented adapter.
- `django-filter` for safe filter APIs where appropriate.
- `Pillow` for image metadata/thumbnail operations where needed.
- Google official Python client libraries where practical.
- `httpx` or `requests` for provider APIs where an official supported client is not appropriate.
- cryptography library for encrypted-at-rest integration credentials.
- pytest + pytest-django for testing.

### Database portability requirement

SQLite is mandatory now, but design the ORM and domain so that PostgreSQL can replace SQLite later without rewriting business logic.

Avoid SQLite-specific assumptions in domain services.

Use UUID primary keys for externally visible business records where practical.

Use database constraints, unique constraints, indexes, and application-level validation intentionally.

## Frontend

Use:

- React 19.x (current stable major; use the latest compatible stable release at implementation time).
- TypeScript, strict mode.
- Vite 8.x/current stable compatible Vite.
- React Router.
- TanStack Query for server state.
- React Hook Form + schema validation (Zod or equivalent).
- Tailwind CSS 4.x.
- Accessible headless primitives where needed; avoid unnecessarily heavy UI frameworks.
- Vitest + React Testing Library.
- Playwright for high-value end-to-end journeys.

## Architecture

Use a monorepo:

```text
creative-manager/
├─ backend/
├─ frontend/
├─ docs/
├─ ops/
├─ scripts/
├─ .env.example
├─ docker-compose.yml
├─ README.md
└─ Makefile or equivalent cross-platform task documentation
```

---

# 4. STANDALONE PRODUCT ARCHITECTURE

Split Django into bounded apps.

Recommended structure:

```text
backend/
├─ config/
├─ apps/
│  ├─ accounts/
│  ├─ workspaces/
│  ├─ catalog/
│  ├─ requests_app/
│  ├─ creatives/
│  ├─ storage/
│  ├─ integrations/
│  ├─ performance/
│  ├─ experiments/
│  ├─ automations/
│  ├─ context_hub/
│  ├─ notifications/
│  ├─ audit/
│  └─ common/
└─ manage.py
```

Do not create one giant `creative_manager` Django app.

Keep business logic in services/domain modules rather than placing complex logic in views, serializers, signals, or model `save()` methods.

Prefer explicit service calls over hidden signal chains.

---

# 5. AUTHENTICATION, USERS, PROFILES, ROLES

The new application is a real multi-user platform.

## User

Implement a custom Django user model from day one.

Recommended fields:

- id UUID
- email unique, primary login identity
- username/display handle optional
- first_name
- last_name
- display_name
- is_active
- is_staff
- is_superuser
- date_joined
- last_login
- last_seen_at

## UserProfile

Fields should include:

- avatar
- job_title
- phone optional
- preferred_language: `ar`, `en`, `fr`
- timezone
- locale
- notification preferences
- theme preference optional
- compact/mobile UI preference if useful

## Authentication model

For the React SPA served from the same deployment/domain, prefer secure Django session authentication:

- HttpOnly session cookie
- CSRF protection
- secure cookies in production
- SameSite configured correctly
- no access token in localStorage

Provide:

- login
- logout
- current-user session endpoint
- password change
- password reset flow
- admin-created/invited user flow
- profile editing
- active/deactivated user state

Do not hard-delete a user who owns business history. Default to deactivation and preserve attribution.

## Roles

Support these roles:

1. Platform Admin
2. Manager
3. Media Buyer
4. Editor
5. Reviewer
6. Requester
7. Viewer

A user can have a different role in different workspaces.

Roles must be membership-based, not a single global `role` column.

## Granular permissions

Preserve/evolve the source permissions:

- create_requests
- assign_editors
- submit_version
- review_version
- approve_version
- create_products
- create_campaigns
- manage_projects
- view_analytics
- view_creatives
- edit_creatives
- comment_creatives
- mark_winner
- manage_performance
- manage_deployments
- manage_experiments
- manage_automations
- publish_ads
- manage_lineage
- manage_boards
- manage_taxonomy
- manage_naming
- manage_workspaces
- manage_clips
- manage_storage_connections
- view_storage_connections
- manage_content_index
- manage_source_materials
- manage_context
- manage_users
- view_audit_log

Use a permission service/policy layer on the backend.

Frontend permission hiding is convenience only and MUST NOT be security enforcement.

---

# 6. WORKSPACES AND BRAND SCOPE

Implement:

## Workspace

- id
- name
- slug
- description
- active
- created_by
- timestamps

## WorkspaceMembership

- workspace
- user
- role
- active
- joined_at

Unique `(workspace, user)`.

## Brand

- workspace
- name
- slug
- logo
- active
- metadata

## Brand access restrictions

A workspace member can optionally be restricted to selected brands.

Manager/platform admin can configure brand restrictions.

All business queries must pass through a clear workspace/brand scope mechanism.

Never trust `workspace_id` supplied by the frontend without verifying membership.

Add tests proving users cannot access records from another workspace or unauthorized brand.

---

# 7. CATALOG

Implement catalog entities:

- Brand
- Product
- Campaign
- Platform
- Project if useful after auditing legacy behavior
- Tag
- Taxonomy
- AttributeValue
- NamingTemplate

Platforms initially include:

- Meta
- TikTok
- YouTube
- Google Ads
- Snapchat
- Pinterest
- LinkedIn
- Other

Products and campaigns belong to a workspace/brand.

Use archive/deactivate semantics where deleting would break history.

---

# 8. REQUEST WORKFLOW

## CreativeRequest

Core fields:

- UUID
- human-readable code, e.g. `REQ-2026-000123`
- workspace
- brand
- product optional
- campaign optional
- requester
- primary owner optional
- title
- objective
- details
- priority
- due_date
- status
- requested platforms
- timestamps
- completed_at
- published_at where relevant

Preserve request statuses:

```text
new
assigned
in_production
ready_for_review
changes_requested
approved
published
refresh_requested
```

## RequestDeliverable

A request may contain multiple deliverables.

Fields may include:

- request
- sequence
- title
- creative_type
- platform
- format/aspect ratio
- quantity
- duration target
- requirements
- assigned_editor
- due date
- status
- linked creative(s)

Unique sequence per request.

## Source materials

Implement:

- RequestSourceMaterial
- SourceMaterialUsage

Allow:
- link
- uploaded file
- Drive file
- text note/reference

Track which creative/version used each source item.

## Workflow rules

Transitions must be explicit and validated.

Do not allow arbitrary status mutation.

Create a workflow service/state machine with:
- allowed transitions;
- actor/permission validation;
- transition timestamps;
- audit entry;
- notification generation.

---

# 9. PRODUCTION BOARD AND MY TASKS

## Board

Provide a clean Kanban view over real workflow data.

Do not duplicate the source of truth just to render a board.

If custom boards are retained, model them cleanly, but request/deliverable status remains authoritative.

Views:

- Production Board
- My Tasks
- Waiting for Review
- Due Soon
- Overdue
- Recently Approved

Role behavior:

- Editor: assigned production work
- Reviewer: review queue
- Manager: complete overview
- Media Buyer: request/deployment overview
- Requester: own request tracking

Support filters:
- brand
- product
- campaign
- editor
- reviewer
- status
- priority
- due date
- platform

---

# 10. CREATIVE DOMAIN — THE CENTER OF THE PLATFORM

## Creative

Fields should include:

- UUID
- human code e.g. `CR-2026-000321`
- workspace
- brand
- request
- deliverable optional
- product/campaign references
- name/title
- description
- creative type
- owner/editor
- current status
- current_version
- approved_version
- outcome summary
- archived_at
- timestamps

The Creative is not the same thing as an ad deployment.

A single Creative may be deployed multiple times across campaigns/platforms.

## CreativeVersion

Append-only version history.

Fields:

- creative
- version_number
- label
- version_type
- editor
- notes
- status
- submitted_at
- approved_at
- published_at
- timestamps

Statuses:

```text
draft
submitted
changes_requested
approved
published
```

Constraints:

- unique `(creative, version_number)`
- version numbers never silently reused
- previous approved/version history is preserved
- approving a new version never destroys old evidence
- no publication from draft/submitted/changes_requested

## Comments and feedback

Implement:

- CreativeComment
- CreativeFeedback

Feedback must support:
- author
- target version
- text
- category if useful
- resolved state
- created/resolved timestamps

One clear conversation experience should be presented in the UI even if structured feedback is stored separately.

---

# 11. REVIEW / APPROVAL UX

Provide explicit primary actions according to role and state.

Examples:

Editor:
- Save Draft
- Submit for Review

Reviewer:
- Approve
- Request Changes

Manager:
- Reassign
- Approve if permitted
- Mark outcome

Do not overload pages with many equally prominent actions.

Use progressive disclosure for advanced sections.

Every transition must generate:
- AuditEvent
- Activity event
- appropriate Notification

---

# 12. CREATIVE FILES AND MEDIA IDENTITY

## CreativeFile

Store metadata, not merely a URL.

Fields:

- creative
- version optional
- file role:
  - master
  - source
  - thumbnail
  - subtitle
  - export
  - reference
  - attachment
- provider
- storage object
- filename
- MIME type
- size
- checksum where available
- width/height/duration where available
- active
- timestamps

Avoid duplicates by provider identity and checksum where reasonable.

A Publishing job must resolve an approved **master asset** deterministically.

If it cannot, fail with a helpful error.

---

# 13. GOOGLE DRIVE — FIRST-CLASS STORAGE

Google Drive is a major part of the platform, not a simple link field.

## Storage strategy

The database is the source of truth for:
- relationships
- business states
- IDs
- permissions
- audit history
- external metadata

Google Drive is the primary managed binary asset store.

Never make business logic depend on folder names alone.

Use Drive file/folder IDs as durable identity.

## StorageConnection

Fields:

- workspace
- provider = google_drive
- account identity/email
- root folder ID
- Shared Drive ID optional
- encrypted OAuth refresh credentials
- scopes
- connection status
- last successful sync
- error state
- created_by
- timestamps

Encrypt secrets using a dedicated environment encryption key.

## Production storage preference

Support both My Drive and Shared Drives.

For company-owned assets, prefer a **Google Shared Drive** when available because asset ownership should belong to the organization rather than one employee.

## OAuth

Implement proper Google OAuth 2.0:
- state validation
- PKCE if supported/appropriate for chosen flow
- encrypted refresh token
- token refresh
- revoked credential handling
- disconnect
- connection test

Choose the narrowest practical scopes.

Default toward `drive.file` when the workflow only needs files created/explicitly selected by the application.

If broader browsing/sync of an existing Drive hierarchy requires broader Drive scopes, make this an explicit admin choice and document Google verification implications.

Never send refresh tokens to React.

## Drive folder organization

Create a stable application root, e.g.:

```text
CreativeManager/
└─ Workspaces/
   └─ {workspace-code}_{workspace-slug}/
      └─ Brands/
         └─ {brand-code}_{brand-slug}/
            ├─ Products/
            ├─ Campaigns/
            │  └─ {YYYY}/
            │     └─ {campaign-code}_{campaign-slug}/
            │        └─ Requests/
            │           └─ {request-code}/
            │              ├─ 01_Source_Materials/
            │              ├─ 02_Working/
            │              ├─ 03_Approved/
            │              └─ 04_Published/
            ├─ Creatives/
            │  └─ {creative-code}/
            │     ├─ Versions/
            │     │  ├─ v001/
            │     │  ├─ v002/
            │     │  └─ ...
            │     ├─ Masters/
            │     ├─ Thumbnails/
            │     └─ Exports/
            ├─ Clips/
            ├─ Context/
            └─ Archive/
```

Do not repeatedly search Drive by path to resolve folders.

Create a `DriveFolderMapping` table:

- workspace
- brand optional
- entity_type
- entity_id
- folder_role
- drive_folder_id
- connection
- timestamps

Use folder ID mapping as the authoritative link.

## appProperties

Where useful, tag app-created Drive items with `appProperties`, for example:

- app = creative_manager
- workspace_id
- brand_id
- request_id
- creative_id
- version_id
- file_role

Do not rely exclusively on these properties; database mappings remain primary.

## Upload behavior

Implement resumable upload for large files.

Design upload states:

```text
queued
initializing
uploading
verifying
complete
failed
cancelled
```

Store:
- idempotency key
- resumable session URI encrypted or protected as appropriate
- total bytes
- uploaded bytes
- attempts
- last error
- external file ID
- timestamps

Uploads must be resumable after transient failures.

Do not mark complete before Drive confirms the file.

## Drive sync

Implement:
- initial inventory sync
- incremental sync where practical using Drive change tracking
- deleted/moved/renamed file reconciliation
- duplicate detection
- orphan reporting
- sync run audit
- clear error reporting

Renaming a Drive folder must not break DB relationships.

## Existing file attachment

Allow authorized users to:
- select/search existing Drive files accessible through the configured connection;
- attach a Drive object to a Creative/Version;
- avoid duplicate storage objects.

---

# 14. LOCAL STORAGE FALLBACK

Retain a local storage provider for:
- development
- tests
- emergency fallback if explicitly configured

Production defaults should be configurable.

Do not mix local and Drive identity silently.

Each file knows its provider.

Temporary upload files must have cleanup routines.

---

# 15. YOUTUBE RESUMABLE UPLOAD

Preserve and rebuild the source module’s YouTube resumable upload capability.

Use YouTube Data API v3 and official resumable upload behavior.

Requirements:

- only approved/publishable creative versions
- deterministic master asset resolution
- resumable session state
- progress bytes
- retries with backoff
- idempotency
- saved video ID only after confirmed success
- safe privacy defaults: `private` or `unlisted`
- no automatic public publish unless an authorized user explicitly selects it
- provider errors displayed in human-readable form
- audit record

Never fabricate a video ID.

---

# 16. CREATIVE LINEAGE / FAMILIES

Implement CreativeRelationship.

Supported relationships:

- variant
- refresh
- remake
- derivative
- localization

Relationships are between **Creatives**, not between CreativeVersions.

Provide family/lineage graph.

Support creating a related creative from a parent while retaining:
- parent link
- change hypothesis
- what changed
- reason
- author

Examples:
- same body, new hook
- new CTA
- localized Arabic/French version
- seasonal refresh

---

# 17. CLIPS AND CONTENT INDEX

## Clip

Represent reusable visual/audio portions.

Fields may include:

- workspace/brand
- source storage object
- title
- start/end timestamps
- description
- tags
- transcript fragment
- created_by

## ClipUsage

Track clips used in creative versions.

This allows later analytics such as:
- which clips appear in winners;
- clip reuse count;
- performance by clip.

## ContentIndexEntry

Support:

- transcript
- OCR
- manually corrected text
- source type
- source object/version
- language
- timestamps

For SQLite, implement full-text search safely using either:
- Django-compatible FTS integration; or
- an isolated SQLite FTS5 adapter with a clean fallback.

Do not scatter raw FTS SQL across the application.

Human corrections must override automated extraction without deleting machine output.

---

# 18. CREATIVE LIBRARY

Build a powerful read/search library.

Filters:
- brand
- product
- campaign
- platform
- creative type
- editor
- status
- outcome
- date
- tags
- family
- used clip
- performance thresholds

Views:
- cards
- compact table
- family view
- creative detail

Show useful summary signals, not excessive clutter.

---

# 19. PERFORMANCE AND DEPLOYMENTS

## Deployment

A Deployment represents usage of a creative/version on an external platform.

Fields:
- creative
- creative version
- provider/platform
- ad connection
- external account ID
- campaign ID/name
- ad set/group ID/name
- ad ID/name
- destination URL
- UTM
- active state
- deployed_at
- sync timestamps

A Creative may have many Deployments.

## PerformanceSnapshot

Store time-series data, not only one mutable total.

Suggested metrics:
- spend
- impressions
- reach
- frequency
- clicks
- link clicks
- CTR
- CPC
- CPM
- conversions
- purchases
- CPA
- revenue/value
- ROAS
- video views
- hook/hold metrics where provider gives them

Each snapshot must record:
- provider
- deployment
- interval start/end
- raw provider payload optionally sanitized
- normalized metrics
- collected_at

Use unique constraints to prevent duplicate windows.

---

# 20. AD PLATFORM CONNECTIONS

Support the existing platform concept for:

- Meta
- TikTok
- Google Ads

Create provider interfaces:

```text
AdConnectionProvider
PerformanceSyncProvider
PublishingProvider
```

Keep these responsibilities separate.

A provider may support performance sync but not publishing.

The UI must show capability flags such as:
- connected
- performance sync supported
- publishing supported
- last sync
- error state

## Production safety

Mocks must be named, e.g.:
- `MockMetaProvider`
- `DeterministicTestProvider`

Production registry must never silently fall back to a mock.

If TikTok or Google publishing is not implemented/authorized, display `Not supported/configured` rather than pretending deployment succeeded.

## Meta publishing

Rebuild safe publishing capability from the legacy module.

Requirements:
- only approved eligible versions;
- validated destination URL;
- resolved master asset;
- explicit connection/account selection;
- create PublishJob;
- record steps;
- store provider receipt/external IDs only from real response;
- retry only idempotent/safe steps;
- avoid duplicate ads on retry;
- audit everything.

---

# 21. PUBLISH JOBS / STEP RECORDING

Implement:

## PublishJob
- workspace
- creative/version
- provider
- connection
- state
- idempotency key
- requested_by
- error
- external receipt
- timestamps

## PublishStep
- job
- sequence
- operation
- status
- provider request fingerprint
- sanitized response metadata
- external ID if confirmed
- attempts
- timestamps

States:

```text
queued
running
waiting
succeeded
failed
cancelled
```

No successful state without provider confirmation.

---

# 22. OUTCOMES AND FATIGUE

Implement OutcomeHistory.

Supported outcome concepts:

- winner
- loser
- neutral
- fatigued
- refresh_requested

Do not overwrite history.

Store:
- outcome
- reason
- actor or automation
- supporting metrics snapshot/reference
- created_at

## Fatigue engine

Use configurable thresholds based on the source behavior, initially:

- minimum impressions: 100
- CTR drop warning: ~25%
- ROAS drop warning: ~25%
- CPA rise warning: ~30%
- frequency warning: ~2.5

These are defaults, not immutable truth.

Make them configurable per workspace.

Fatigue should generate a **signal**, not silently alter data without audit.

---

# 23. EXPERIMENTS

Implement:

## Experiment
- creative/family/campaign context
- title
- hypothesis
- primary KPI
- secondary KPI
- status
- start/end dates
- conclusion
- learning
- next action

## ExperimentArm
- experiment
- name
- control flag
- creative/version/deployment binding

Lifecycle:

```text
draft
running
completed
cancelled
```

Completion should support:
- selected winner if user decides;
- evidence notes;
- metric comparison;
- confidence/limitations notes.

Do not pretend causal certainty merely because one number is higher.

---

# 24. PATTERNS, EVIDENCE ASSISTANT, PROPOSALS

Rebuild the legacy intelligence features as useful evidence tools.

## Pattern analysis

Support grouped observations such as:
- hook type
- format
- duration
- CTA
- product
- clip
- platform
- family
- outcome

Display sample size and time period.

Avoid presenting weak correlations as proven causes.

## Evidence Assistant

Provide a query/filter interface that can answer questions using stored creative evidence.

Examples:

- winning hair-loss creatives using question hooks;
- creatives whose CTR declined after day 5;
- variants that outperformed their parent;
- clips repeatedly used in winners.

Evidence Assistant initially uses database evidence.

If an AI analysis provider is later added:
- it must cite internal source records;
- it must not fabricate metrics;
- AI output is advisory only.

## Creative proposals

Support proposals derived from evidence:
- proposed change
- source creatives/evidence
- rationale
- status
- accepted/rejected
- resulting creative link

---

# 25. CONTEXT HUB / KNOWLEDGE

Implement:

## ContextDocument

Examples:
- brand guidelines
- product facts
- allowed claims
- forbidden claims
- audience notes
- tone/voice
- platform rules
- campaign guidance

## ContextDocumentVersion

Version all context edits.

Statuses:

```text
draft
approved
archived
```

Do not mutate an approved historical version.

## ContextCreativeLink / Evidence

Allow approved context to be linked to creative families/creatives.

Support brand scope.

---

# 26. AUTOMATION ENGINE

Rebuild automation using explicit rules.

Entities:

- AutomationRule
- AutomationCondition
- AutomationAction
- AutomationRun
- AutomationRunStep

Examples:

```text
IF request becomes ready_for_review
THEN notify reviewers
```

```text
IF creative receives fatigued signal
THEN create refresh recommendation
```

```text
IF approved version has no deployment after N days
THEN notify Media Buyer
```

Safety:

- actions must be allow-listed;
- no arbitrary Python/eval/code execution;
- every run recorded;
- idempotent actions;
- retry tracking;
- prevent recursive loops;
- support enabled/disabled state.

External publishing should NOT be automatically triggered by a generic rule unless a dedicated high-safety feature is explicitly enabled and permissioned.

---

# 27. NOTIFICATIONS

Add a first-class in-app Notification system.

Notification types should include at least:

- new request
- assignment
- feedback
- changes requested
- ready for review
- approved
- deadline approaching
- overdue
- winner/loser/fatigue
- refresh requested
- workflow changed
- integration failure
- upload completed/failed
- publish completed/failed

Features:

- unread count
- mark read
- mark all read
- deep link
- user notification preferences
- deduplication to avoid spam
- role-aware recipients

Avoid requiring WebSockets for v1.

Efficient polling is acceptable and simplifies SQLite deployment.

---

# 28. ACTIVITY AND AUDIT LOGGING

These are separate concepts.

## Activity Feed

Human-friendly operational events:
- request created
- assigned
- version submitted
- feedback added
- approved
- deployed
- winner marked

## AuditEvent

Immutable security/business audit:

- actor
- workspace
- action
- object type
- object ID
- before/after summary where safe
- IP
- user agent
- request correlation ID
- timestamp

Do not store secrets or giant provider payloads.

Audit important:
- role/membership changes
- integrations
- publishing
- approval
- outcome
- deletion/archive
- credential changes

---

# 29. UTM BUILDER

Preserve UTM Builder.

Fields:

- base URL
- source
- medium
- campaign
- term
- content

Features:

- validation
- encoding
- copy result
- optional history linked to Campaign/Deployment
- workspace naming conventions

---

# 30. DASHBOARDS

Provide role-specific dashboards.

## Manager
- open requests
- work in production
- review queue
- overdue
- approved this period
- publish failures
- integration failures
- winners/fatigued
- team workload

## Media Buyer
- requests created
- approved but undeployed
- deployments
- last performance sync
- top performance table
- fatigue signals
- experiments

## Editor
- My Tasks
- due today
- changes requested
- submitted items
- recent feedback

## Reviewer
- waiting for review
- aging review queue
- recently reviewed

## Requester
- own requests
- status
- delivery progress
- due dates

## Viewer
- library summary/read-only

No fake KPI numbers.

---

# 31. SEARCH

Implement global scoped search across:

- requests
- deliverables
- creatives
- creative versions
- products
- campaigns
- clips
- context
- content index
- Drive file metadata

Results must respect workspace/brand permissions.

---

# 32. FRONTEND UX REQUIREMENTS

The old module should be treated as functional reference, not as a visual template.

Build a modern SaaS interface.

Principles:

- mobile-first;
- responsive;
- Arabic RTL is first-class;
- English/French LTR;
- no horizontal overflow;
- clear typography;
- compact but readable;
- one dominant next action per workflow state;
- progressive disclosure;
- avoid giant forms;
- sticky action areas only when useful;
- clear empty states;
- clear error recovery;
- skeleton/loading states;
- accessible form labels and keyboard navigation;
- confirmation for destructive/high-impact actions.

Main navigation:

```text
Overview
Board
Requests
My Tasks
Creative Library
Search
Context
UTM Builder
Activity
Operations
Automations
Integrations
Catalog
Administration
```

Navigation is permission-aware.

Create a mobile navigation solution, not merely a collapsed desktop sidebar.

---

# 33. INTERNATIONALIZATION

Support:

- Arabic (`ar`) — RTL
- English (`en`)
- French (`fr`)

Backend and frontend should use translatable keys.

No hard-coded English scattered through React components.

Provide locale switcher and persist preference in UserProfile.

Dates/numbers should render according to locale where practical.

---

# 34. BACKGROUND JOBS WHILE KEEPING SQLITE

This platform has long-running operations:

- Drive upload
- Drive sync
- YouTube upload
- provider performance sync
- publishing
- automation runs
- media metadata extraction

Do not execute long external operations inside normal web requests.

For this SQLite-first deployment, implement a lightweight internal Job system.

## Job model

- type
- payload JSON
- status
- priority
- attempts
- max attempts
- available_at
- claimed_at
- heartbeat_at
- completed_at
- failed_at
- last_error
- idempotency_key
- workspace
- created_by

## Worker

Implement a management command, e.g.:

```bash
python manage.py run_worker
```

Requirements:

- single production worker by default for SQLite;
- atomic claim;
- retries;
- exponential backoff;
- stale job recovery;
- graceful shutdown;
- idempotent handlers;
- logs/correlation ID.

Architect the queue behind an interface so Redis/Celery/Dramatiq can replace it later without rewriting domain services.

Do not use SQLite on an NFS/network filesystem.

---

# 35. SQLITE PRODUCTION HARDENING

The user explicitly requested SQLite.

Use it responsibly:

- enable WAL mode at application startup/connection configuration where safe;
- configure a reasonable busy timeout;
- short transactions;
- do not keep DB transactions open during external HTTP calls;
- use one background worker by default;
- index frequent filters;
- persistent local disk/volume;
- automated backups;
- integrity-check documentation.

Add documented commands:

```bash
python manage.py backup_database
python manage.py restore_database ...
python manage.py check
```

A backup must include:
- SQLite DB
- local media/temp files if production uses them
- encryption key backup instructions (never embed key in backup logs)

Google Drive assets themselves do not need to be duplicated into the DB backup, but Drive IDs and metadata do.

---

# 36. SECURITY

Required production controls:

- `DEBUG=False`
- strong `SECRET_KEY`
- separate `APP_ENCRYPTION_KEY`
- allowed hosts
- trusted CSRF origins
- HTTPS
- secure cookies
- HSTS when HTTPS configuration is verified
- clickjacking protection
- MIME validation for uploads
- file size limits
- filename sanitization
- authorization on every object read/write
- provider timeout configuration
- retry limits
- SSRF-safe URL validation where server fetches are used
- destination URL validation
- no secrets in logs
- sanitized provider errors
- dependency audit
- CSP where practical
- rate limiting for login and sensitive endpoints
- server-side validation even if React validates too

Do not deserialize arbitrary Python objects.

Do not use `eval`.

Do not execute user-provided automation code.

---

# 37. API DESIGN

Use `/api/v1/`.

Use RESTful resources with domain actions only when they represent real workflow transitions.

Examples:

```text
/api/v1/auth/session
/api/v1/me
/api/v1/users
/api/v1/workspaces
/api/v1/workspaces/{id}/members
/api/v1/brands
/api/v1/products
/api/v1/campaigns

/api/v1/requests
/api/v1/requests/{id}
/api/v1/requests/{id}/deliverables
/api/v1/requests/{id}/assign
/api/v1/requests/{id}/start-production

/api/v1/creatives
/api/v1/creatives/{id}
/api/v1/creatives/{id}/versions
/api/v1/creatives/{id}/comments
/api/v1/creatives/{id}/submit
/api/v1/creatives/{id}/approve
/api/v1/creatives/{id}/request-changes

/api/v1/storage/connections
/api/v1/storage/connections/{id}/sync
/api/v1/storage/drive/uploads
/api/v1/storage/objects

/api/v1/deployments
/api/v1/performance
/api/v1/experiments
/api/v1/automations
/api/v1/context
/api/v1/notifications
/api/v1/audit
```

Use pagination consistently.

Return structured validation errors.

Use correlation/request IDs.

Avoid endpoints that expose unscoped global data.

---

# 38. DATA MODEL INVARIANTS

Codex must encode and test important invariants.

At minimum:

1. A workspace member cannot access another workspace’s records.
2. Brand-restricted members only see allowed brands.
3. CreativeVersion number is unique per creative.
4. Approved/published versions are never silently overwritten.
5. Publishing requires an approved eligible version.
6. Publishing requires a resolvable active master asset.
7. External provider success requires confirmed provider response.
8. Drive object identity uses connection + external file ID, not filename.
9. Folder relationships use Drive folder IDs, not only path strings.
10. Performance snapshots are time-stamped and historical.
11. Outcome changes append history.
12. Experiment arms cannot reference inaccessible creatives.
13. Source material usage is traceable.
14. All permission changes are audited.
15. OAuth credentials never appear in normal API serializers.
16. Background jobs are idempotent.
17. A retry cannot create duplicate external publications if the provider supports idempotent resolution.
18. Hard deletion of business history is restricted.
19. Every workflow transition validates the current state.
20. Test providers never load in production provider registry.

---

# 39. LEGACY IMPORT / MIGRATION

Add an optional migration tool so data from the old PHP CreativeManager can be brought into the new system.

Preferred management command:

```bash
python manage.py import_legacy_creativemanager --database /path/to/old.sqlite --dry-run
```

and then:

```bash
python manage.py import_legacy_creativemanager --database /path/to/old.sqlite
```

Requirements:

- dry run;
- validation report;
- counts per table/entity;
- orphan report;
- duplicate report;
- transaction per safe batch;
- resumable/checkpointed import where practical;
- mapping table from legacy IDs to new UUIDs;
- never modify source DB;
- import audit record.

Map legacy `in_review` safely rather than creating an invalid new status; determine context and map to `submitted` / request `ready_for_review`.

Import Drive IDs/tokens only if they can be transferred securely and semantically; otherwise require reconnection and preserve non-secret external IDs.

Do not import corrupted records silently.

Create a final migration report.

---

# 40. SEED / DEMO DATA

Provide:

```bash
python manage.py seed_demo
```

Create:

- demo workspace
- demo brand
- products
- campaign
- users for each role
- example request with multiple deliverables
- creatives and versions
- comments/feedback
- one experiment
- sample performance snapshots

Use clearly fake local demo data only.

Never create fake live provider connections.

Document demo credentials and force password change if used beyond local demo.

---

# 41. TESTING REQUIREMENTS

## Backend

Use pytest.

Required test categories:

- models/constraints
- permissions
- workspace scoping
- brand restrictions
- workflow state machine
- request lifecycle
- creative version lifecycle
- review/approval
- file identity
- Drive mapping
- Drive OAuth state handling
- Drive upload retries
- YouTube resumable state
- provider registry
- publishing safety
- performance normalization
- fatigue signals
- experiment lifecycle
- automation idempotency
- notifications
- legacy importer
- API validation

## Frontend

Use:
- Vitest
- React Testing Library

Test:
- role-dependent rendering
- forms
- workflow actions
- RTL
- query errors
- optimistic updates only where safe
- accessibility basics

## End-to-end Playwright

Must cover at least:

### Journey A — Requester to approved creative
1. Login as requester
2. Create request with 2 deliverables
3. Manager assigns editor
4. Editor starts work
5. Editor creates/submits version
6. Reviewer requests changes
7. Editor creates v2
8. Reviewer/manager approves
9. verify audit/activity/notifications

### Journey B — Drive
1. Admin creates a mock/dev Drive connection or test fixture
2. Upload/attach asset
3. verify storage identity
4. rename/move simulation
5. verify relationship survives ID-based sync

### Journey C — Media Buyer
1. Approved creative
2. create deployment
3. ingest performance
4. compare snapshots
5. create outcome/refresh

### Journey D — Experiment
1. create parent/variant
2. create experiment
3. bind arms
4. complete experiment
5. record learning

### Journey E — Permissions
Attempt cross-workspace and restricted-brand reads/writes and prove rejection.

## Quality gates

Before completion:

- backend test suite passes
- frontend tests pass
- TypeScript typecheck passes
- frontend production build passes
- lint passes
- Django system check passes
- migrations make/check clean
- Playwright critical paths pass
- no production code depends on mock providers
- no high-severity known dependency vulnerability left unexplained

Aim for high meaningful coverage on domain/workflow services; do not game coverage with meaningless tests.

---

# 42. OBSERVABILITY AND ERROR HANDLING

Add:

- structured application logs
- request/correlation ID
- worker/job logs
- provider name and operation in errors without secrets
- health endpoint
- readiness endpoint
- last integration sync status
- job failure visibility in admin/operations

Health endpoint must not expose secrets.

Operations page should surface:
- failed background jobs
- stale jobs
- failed uploads
- failed publishing
- disconnected providers
- old performance sync
- Drive sync errors

---

# 43. DJANGO ADMIN

Use Django Admin as an emergency/operations interface, not as the main product UI.

Register important models.

Admin permissions must remain safe.

Sensitive token fields must be hidden/redacted.

Useful admin features:
- search
- filters
- readonly IDs/external identity
- audit visibility
- retry job action only if safe
- deactivate user

---

# 44. DEPLOYMENT

Provide both simple native deployment and Docker deployment.

## Docker production shape

Recommended:

```text
nginx
  ├─ serves React build
  └─ proxies /api and /admin to Django

django web
django worker
persistent local SQLite volume
```

If the same image is used for web and worker, use different commands.

Do not put SQLite on distributed/network storage.

## Django server

Use a production WSGI/ASGI server appropriate to the implemented features.

Do not use Django `runserver` in production.

## Static frontend

Build React once:

```bash
npm run build
```

Serve static assets via Nginx or another production web server.

## Environment

Provide `.env.example` with explanations.

At minimum:

```env
DJANGO_SECRET_KEY=
APP_ENCRYPTION_KEY=
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=
DJANGO_CSRF_TRUSTED_ORIGINS=
DATABASE_PATH=/data/creative_manager.sqlite3

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

META_APP_ID=
META_APP_SECRET=
META_REDIRECT_URI=

TIKTOK_CLIENT_ID=
TIKTOK_CLIENT_SECRET=

GOOGLE_ADS_...

YOUTUBE_...

MAX_UPLOAD_BYTES=
```

Only include variables actually used.

Never commit real secrets.

---

# 45. GOOGLE CLOUD SETUP DOCUMENTATION

Create `docs/GOOGLE_SETUP.md`.

Explain step-by-step:

1. create/select Google Cloud project;
2. enable Drive API;
3. enable YouTube Data API if YouTube upload is used;
4. configure OAuth consent screen;
5. create Web OAuth client;
6. configure authorized redirect URI;
7. choose scopes;
8. connect inside CreativeManager;
9. select/create application Drive root;
10. Shared Drive recommendation;
11. token revocation/reconnection;
12. common errors.

Use current official Google documentation while implementing.

---

# 46. WINDOWS LOCAL DEVELOPMENT DOCUMENTATION

Create `docs/WINDOWS_LOCAL_SETUP.md`.

Assume a Windows user using Command Prompt or PowerShell.

Include exact commands for:

- install Python 3.13
- create venv
- activate venv
- install backend dependencies
- create `.env`
- migrate
- create superuser
- seed demo
- run Django
- install Node
- install frontend dependencies
- start Vite
- run tests

Example shape:

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Then frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Use the actual resulting commands/configuration, not placeholder instructions.

---

# 47. BACKUP / RESTORE

Provide tested commands.

Backup should create timestamped copies safely.

Before copying SQLite:
- use SQLite backup API or safe checkpoint/backup technique;
- do not blindly copy an actively changing WAL database in an unsafe way.

Provide:
- automatic backup retention config
- manual backup
- restore verification
- `PRAGMA integrity_check` or equivalent through a management command

Document where Google Drive metadata fits into recovery.

---

# 48. DOCUMENTATION OUTPUT

Create:

```text
README.md
docs/
├─ ARCHITECTURE.md
├─ DOMAIN_MODEL.md
├─ WORKFLOWS.md
├─ PERMISSIONS.md
├─ GOOGLE_SETUP.md
├─ PROVIDER_INTEGRATIONS.md
├─ WINDOWS_LOCAL_SETUP.md
├─ DEPLOYMENT.md
├─ BACKUP_RESTORE.md
├─ LEGACY_IMPORT.md
├─ TESTING.md
└─ SECURITY.md
```

Also create Mermaid diagrams where helpful:
- architecture
- request lifecycle
- creative lifecycle
- Drive storage flow
- publishing flow
- entity relationships

---

# 49. IMPLEMENTATION MILESTONES

Codex should execute these automatically.

## Milestone 0 — Legacy audit
- unpack reference ZIP
- inventory all capabilities
- map source models/services/routes/migrations to target domains
- record known defects
- create `docs/LEGACY_AUDIT.md`

## Milestone 1 — Foundation
- Django project
- React project
- config
- custom User
- profiles
- workspaces
- memberships
- roles/permissions
- session auth
- i18n
- base responsive layout
- API conventions
- tests

## Milestone 2 — Catalog + Requests
- brands/products/campaigns/platforms
- requests
- deliverables
- source materials
- assignments
- workflow
- board
- My Tasks
- notifications/activity

## Milestone 3 — Creatives
- creative workspace
- versioning
- comments
- feedback
- review
- approval
- lineage
- creative family
- library
- search

## Milestone 4 — Storage
- local provider
- Google OAuth
- StorageConnection
- Drive folders/mappings
- Drive inventory/sync
- resumable upload
- attach existing
- CreativeFile
- file identity
- UI

## Milestone 5 — Clips + Content
- clips
- clip usages
- transcript/OCR index
- search
- manual corrections

## Milestone 6 — Deployment + Performance
- deployments
- ad connections
- provider interfaces
- performance snapshots
- normalized analytics
- fatigue
- outcome history
- decision UI

## Milestone 7 — Experiments + Knowledge
- experiments
- arms
- comparisons
- context hub
- context versions/evidence
- patterns
- evidence assistant
- creative proposals

## Milestone 8 — Publishing + YouTube
- publish jobs/steps
- real Meta provider behavior
- safe provider registry
- retries/idempotency
- YouTube resumable upload
- external receipt integrity

## Milestone 9 — Automation + Operations
- rule builder
- worker/job infrastructure
- automation runs
- operations dashboard
- failed job tools

## Milestone 10 — Legacy import
- dry run
- import
- mappings
- reports
- edge cases

## Milestone 11 — Production hardening
- security
- rate limits
- backup/restore
- Docker
- Nginx
- health checks
- docs
- deployment
- full regression
- browser/mobile/RTL QA

## Milestone 12 — Final acceptance
- fresh clone installation test
- empty DB migration test
- demo seed test
- production build
- complete tests
- final QA report
- package final standalone ZIP

Do not declare Milestone 12 complete if any blocking test or build is failing.

---

# 50. DEFINITION OF DONE

The platform is considered ready only when a new engineer can:

1. clone/unzip it;
2. follow README;
3. set environment variables;
4. migrate an empty SQLite DB;
5. create an admin;
6. seed demo data;
7. run Django + React locally;
8. log in;
9. create users/workspaces;
10. create a creative request;
11. assign an editor;
12. submit/review/approve creative versions;
13. manage files;
14. connect or configure Google Drive following docs;
15. sync/upload using Drive;
16. create a deployment;
17. store/sync performance;
18. create an experiment;
19. use context/library/search;
20. view notifications/audit;
21. run worker;
22. create/restore a backup;
23. build and deploy production artifacts.

No critical workflow should require editing the database manually.

---

# 51. NON-NEGOTIABLE ANTI-PATTERNS

Do NOT:

- build only UI mockups;
- leave buttons disconnected;
- hard-code demo IDs;
- use localStorage for authentication tokens;
- trust frontend role checks;
- put all business logic in serializers/views;
- execute provider API calls in DB transactions;
- call external APIs synchronously from long user requests where a job is appropriate;
- mark failed integrations successful;
- generate fake provider IDs;
- silently use a mock provider in production;
- use filename as Google Drive identity;
- assume folder path is permanent;
- overwrite history;
- hard-delete audit history;
- expose OAuth tokens;
- make SQLite run on a network share;
- call a feature complete without tests;
- replace the source module with a superficial rewrite.

---

# 52. ENGINEERING JUDGMENT AUTHORITY

You are explicitly authorized to improve the legacy architecture where necessary.

You may:
- normalize poor schema choices;
- rename internal Python classes for clarity;
- split services;
- merge redundant legacy tables when history is preserved;
- improve API design;
- improve UX;
- add missing constraints;
- add audit fields;
- add job infrastructure;
- add health/security/deployment functionality;
- replace legacy patterns with Django best practices.

However:

- preserve the user-visible business capability unless there is a strong reason not to;
- document any intentionally removed legacy behavior;
- do not remove a feature just because porting it is difficult;
- do not invent business behavior that conflicts with the source workflow.

---

# 53. FINAL CODEX RESPONSE FORMAT

When implementation is finished, return a concise final report containing:

## Delivered
A feature-by-feature completion summary.

## Architecture
Actual final stack and major design choices.

## Tests
Exact commands run and results.

## Known limitations
Only real remaining limitations.

## External setup still required
For example provider credentials or Google Cloud OAuth approval.

## Run locally
Exact Windows commands.

## Deploy
Exact production path.

## Files
Links/paths to:
- final ZIP
- README
- final QA report
- migration report if created

Do not hide failed tests.

Do not say “production ready” if critical tests, migrations, authentication, permissions, or persistence are incomplete.

---

# 54. START NOW

Start by unpacking and deeply auditing:

`CreativeManager-v7.2.19-tested-youtube-resumable.zip`

Then create the standalone Django/React project and continue automatically through the milestones.

The reference ZIP is immutable input. Do not overwrite it.

The final product must be independent of the old PHP Core Platform.

Build the complete application, test it thoroughly, and leave it in a state that can actually be used and deployed.
