from pathlib import Path
import re,csv,hashlib
root=Path(__file__).resolve().parents[1]
spec=Path.home()/'Downloads'/'CREATIVEMANAGER_DJANGO_REACT_MASTER_CODEX_BUILD_SPEC.md'
lines=spec.read_text(encoding='utf-8').splitlines()
(root/'docs'/'MASTER_BUILD_SPEC.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
evidence={
0:('Partial acceptance','README.md; FINAL_QA_REPORT.md; KNOWN_LIMITATIONS.md'),
1:('Core lifecycle implemented','backend/apps; frontend/src/App.tsx; tests/test_domain.py'),
2:('Static audit performed','LEGACY_AUDIT.md; legacy-inventory.json'),
3:('Implemented','backend/requirements.txt; frontend/package-lock.json'),
4:('Implemented','backend/apps; ARCHITECTURE.md'),
5:('Implemented core; advanced UI partial','accounts; workspaces/policies.py; tests/test_api.py'),
6:('Implemented and isolation tested','workspaces; common/serializers.py; tests/test_api.py'),
7:('Catalog persistence/UI implemented','catalog; resources.py'),
8:('Core workflow tested','requests_app/services.py; e2e/journeys.spec.ts'),
9:('Core board/tasks; advanced filters partial','frontend/src/App.tsx'),
10:('Core version lifecycle tested','creatives/services.py; tests/test_domain.py'),
11:('Browser-tested review journey','e2e/journeys.spec.ts'),
12:('Local identity/master resolution tested; media processing partial','storage/services.py; tests/test_domain.py'),
13:('Partial; live acceptance and full hierarchy outstanding','storage/google.py; GOOGLE_SETUP.md; tests/test_providers.py'),
14:('Implemented local fallback','storage/services.py'),
15:('Transport tested; live acceptance outstanding','storage/google.py; tests/test_providers.py'),
16:('Relationship records and variant action; graph partial','creatives/services.py; frontend/src/App.tsx'),
17:('Manual clips/index/corrections; extraction and FTS outstanding','storage/models.py; common/serializers.py; SearchView'),
18:('Library implemented; advanced filters partial','frontend/src/App.tsx'),
19:('Historical/manual performance implemented','performance; tests/test_domain.py; e2e/extended.spec.ts'),
20:('Partial provider coverage','performance/providers.py; integrations/services.py; PROVIDER_INTEGRATIONS.md'),
21:('Ledger/safety implemented; live acceptance outstanding','integrations/services.py; tests/test_domain.py'),
22:('Outcomes/fatigue implemented and tested','performance/services.py; context_hub/evidence.py'),
23:('Lifecycle/learning tested; statistical comparisons partial','experiments/services.py; e2e/extended.spec.ts'),
24:('Partial evidence/proposals','context_hub/evidence.py; frontend/src/Evidence.tsx'),
25:('Versioned context implemented','context_hub/services.py'),
26:('Allow-listed reactive rules; richer builder partial','automations/services.py; tests/test_domain.py'),
27:('Core notifications and deadline scan','notifications/services.py; audit/services.py'),
28:('Core immutable API audit/activity','audit; common/admin.py'),
29:('Implemented and tested','frontend/src/App.tsx; App.test.tsx'),
30:('Real counts; role-specific summaries partial','OverviewView; frontend/src/App.tsx'),
31:('Scoped fallback search implemented','SearchView; tests/test_api.py'),
32:('Responsive core UI browser-tested; advanced editors partial','frontend/src; e2e/journeys.spec.ts'),
33:('Partial advanced translation coverage','frontend/src/i18n.tsx; KNOWN_LIMITATIONS.md'),
34:('Queue/claim/retry implemented; long-sync heartbeat gap','common/jobs.py; tests/test_domain.py'),
35:('SQLite hardening and recovery verified','config/settings.py; BACKUP_RESTORE.md'),
36:('Core controls tested; production security acceptance pending','SECURITY.md; dependency-audit-*.json'),
37:('Scoped REST API implemented','config/urls.py; common/views.py'),
38:('Important invariant tests; not exhaustive','backend/tests; FINAL_QA_REPORT.md'),
39:('Conservative partial importer tested','common/legacy.py; LEGACY_IMPORT.md'),
40:('Demo command tested; no live connections','seed_demo.py'),
41:('Executed gates recorded; full acceptance incomplete','FINAL_QA_REPORT.md'),
42:('Health/logs/job records implemented; aggregates partial','middleware.py; jobs.py; operations UI'),
43:('Read-only operations admin; safe user deactivation','common/admin.py; accounts/admin.py'),
44:('Native build verified; Docker runtime blocked by host I/O','DEPLOYMENT.md; docker-compose.yml'),
45:('Delivered','GOOGLE_SETUP.md'),46:('Delivered','WINDOWS_LOCAL_SETUP.md'),47:('Commands and restore integrity verified','BACKUP_RESTORE.md'),48:('Delivered','docs/'),49:('Partial milestone completion','REQUIREMENTS_TRACEABILITY.md'),50:('Not fully production accepted','KNOWN_LIMITATIONS.md'),51:('Core anti-patterns guarded; verify remaining scope','backend/tests; SECURITY.md'),52:('Architecture choices documented','ARCHITECTURE.md'),53:('Report delivered','FINAL_QA_REPORT.md'),54:('Implementation performed; full parity incomplete','README.md')}
headings=[];section=0;review=[]
for i,line in enumerate(lines,1):
    match=re.match(r'^# (\d+)\. (.+)',line)
    if match:section=int(match[1]);headings.append((section,i,match[2]))
    if line.strip():review.append({'source_line':i,'section':section,'spec_text':line,'section_status':evidence.get(section,('Review',''))[0],'evidence':evidence.get(section,('',''))[1]})
with (root/'docs'/'REQUIREMENTS_LINE_MAP.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(review[0]));writer.writeheader();writer.writerows(review)
text='# Specification traceability\n\nEvery numbered section was reviewed. Status is intentionally explicit about partial acceptance. The line-level CSV preserves every nonempty source line and maps it to its section evidence; a section status is not a claim that every bullet is complete.\n\n| Section | Source line | Requirement | Status | Evidence |\n| --- | --- | --- | --- | --- |\n'
for number,line,title in headings:
    status,paths=evidence[number];text+=f'| {number} | {line} | {title} | {status} | {paths} |\n'
text+='\nThe definition of done and milestone 12 remain unaccepted until the listed provider, migration, feature-parity and Docker/production gaps are resolved. See KNOWN_LIMITATIONS.md.\n'
(root/'docs'/'REQUIREMENTS_TRACEABILITY.md').write_text(text,encoding='utf-8')
zip_path=Path.home()/'Downloads'/'CreativeManager-v7.2.19-tested-youtube-resumable.zip'
(root/'docs'/'SOURCE_HASHES.txt').write_text(f'{hashlib.sha256(spec.read_bytes()).hexdigest()}  {spec.name}\n{hashlib.sha256(zip_path.read_bytes()).hexdigest()}  {zip_path.name}\n',encoding='utf-8')
print(f'Mapped {len(review)} source lines across {len(headings)} numbered sections.')
