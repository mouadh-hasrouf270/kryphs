from pathlib import Path
import hashlib,json,re,collections
root=Path(__file__).resolve().parents[1]
source=root.parent/'reference'/'CreativeManager'
inventory=[]
for path in sorted(source.rglob('*')):
    if not path.is_file():continue
    raw=path.read_bytes();content=raw.decode('utf-8',errors='replace')
    inventory.append({'path':path.relative_to(source).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'functions':re.findall(r'function\s+(\w+)\s*\(',content),'tables':sorted(set(re.findall(r'CREATE TABLE IF NOT EXISTS\s+(\w+)',content))),'core_dependencies':sorted(set(re.findall(r'use (App\\(?:Core|Database|Auth)[^;]+);',content)))})
(root/'docs'/'legacy-inventory.json').write_text(json.dumps(inventory,indent=2,ensure_ascii=False),encoding='utf-8')
counts=collections.Counter(p['path'].split('/')[0] for p in inventory)
text='''# Legacy audit

The supplied ZIP remains unchanged. All extracted files were inventoried with SHA-256 hashes, function names, schema definitions and Core dependency imports. See `legacy-inventory.json` for the complete file-level inventory. This is a static audit; PHP was not executed against the absent Core Platform.

## Inventory

'''+ '\n'.join(f'- {name}: {count} files' for name,count in sorted(counts.items()))+'''

## Behavioral findings and target mapping

| Legacy area | Target implementation |
| --- | --- |
| WorkflowService, CreativeRequest aggregate state | requests_app/services.py and creatives/services.py |
| WorkspaceScope, mutation policies, brand users | workspaces/policies.py; scoped relation serializers |
| Core user/notification dependencies | Custom email User, memberships, profile, notifications |
| Version review and refresh history | Append-only version API, explicit state transitions, lineage |
| FileIdentityService, StorageObject split | storage models; connection plus external ID unique identity |
| Drive OAuth and upload transports | storage/google.py; state+PKCE, encrypted refresh/session values |
| PublishingService, PublishingStepRecorder, Meta provider | integrations/services.py; write-ahead step ledger |
| PerformanceAnalysis, FatigueSignalService | performance/services.py; compatible windows, no zero-denominator fabrication |
| Experiments and family evidence | experiments/services.py and context_hub/evidence.py |
| ContextHubService and context evidence | Immutable context version endpoints and scoped evidence links |
| AutomationEngine | Allow-listed actions and uniquely keyed automation runs |
| Old Core deployment | Standalone Django, React, SQLite, worker and Nginx |

The source explicitly distinguishes request orders, planned deliverables, creative executions and version artifacts. Sibling creatives progress independently; a request's aggregate status cannot authorize publication of an unapproved sibling. Review requires submitted versions; change requests require feedback; self-review is restricted outside manager privileges. These rules are preserved in domain tests.

Drive filenames are display metadata; IDs remain authoritative through moves and renames. Resumable session URIs are credentials. Meta writes may be ambiguous after a timeout: the new ledger deliberately prevents automatic replay of an uncertain step. The legacy provider's paused-ad default is preserved.

Fatigue compares compatible currencies/providers and approximately equal observation durations, requires minimum impressions, and emits evidence signals. It does not silently turn a creative into a loser.

## Known source defects addressed by rebuilding

- PHP destination-validation syntax error: replaced by tested HTTPS destination validation.
- Evidence assistant PHP control-flow error: no PHP templates are retained.
- Legacy importer `in_review`: mapped to submitted (versions) or ready_for_review (requests).
- SQL placeholder mismatch: target inserts use Django ORM.
- Stale workspace import: scope is derived from explicit related records; orphan reports prevent silent imports.
- Missing `common.save`: the new UI has a translated save key.
- Referenced but absent legacy tests: the target contains executable pytest, Vitest and Playwright tests.
- Legacy CSS/JS bundles: none are loaded by the standalone app.

## Deliberate changes and remaining gaps

Business history is protected from hard deletion through the API/admin. UUIDs replace sequential database identities. Public human codes use a year and random collision-resistant suffix. No legacy cookies, sessions, PHP controllers, Core permissions or plaintext secrets are retained.

See REQUIREMENTS_TRACEABILITY.md and KNOWN_LIMITATIONS.md for incomplete parity. The existence of a model or endpoint is not a claim that every legacy behavior has passed acceptance testing.
'''
(root/'docs'/'LEGACY_AUDIT.md').write_text(text,encoding='utf-8')
print(dict(counts))
