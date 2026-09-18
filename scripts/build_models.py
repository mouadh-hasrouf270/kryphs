"""Reproducible initial schema generation; generated modules are normal Django code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / 'backend'
APPS = 'accounts workspaces catalog requests_app creatives storage integrations performance experiments automations context_hub notifications audit common'.split()
def write(path, content):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.strip() + '\n', encoding='utf-8')
for app in APPS:
    write(f'backend/apps/{app}/__init__.py', '')
    write(f'backend/apps/{app}/migrations/__init__.py', '')
write('backend/apps/__init__.py', '')
write('backend/config/__init__.py', '')
write('backend/manage.py', '''import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
''')
write('backend/config/wsgi.py', '''import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
''')
write('backend/apps/common/models.py', '''import uuid
from django.conf import settings
from django.db import models

class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True
        ordering = ['-created_at']

class Scoped(Record):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.PROTECT)
    brand = models.ForeignKey('catalog.Brand', on_delete=models.PROTECT, null=True, blank=True)
    class Meta(Record.Meta):
        abstract = True

class Job(Scoped):
    type = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='queued')
    priority = models.IntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    available_at = models.DateTimeField(default=__import__('django.utils.timezone', fromlist=['now']).now)
    claimed_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    failed_at = models.DateTimeField(null=True)
    last_error = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=200, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    class Meta(Scoped.Meta):
        indexes = [models.Index(fields=['status', 'available_at'])]

class LegacyMapping(Record):
    source = models.CharField(max_length=64)
    table = models.CharField(max_length=100)
    legacy_id = models.CharField(max_length=100)
    target_id = models.UUIDField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','table','legacy_id'], name='legacy_identity')]
''')
write('backend/apps/accounts/models.py', '''import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    use_in_migrations = True
    def create_user(self, email, password=None, **extra):
        if not email: raise ValueError('Email is required')
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user
    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    last_seen_at = models.DateTimeField(null=True)
    must_change_password = models.BooleanField(default=False)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()
    def __str__(self): return self.display_name or self.email

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='profile')
    avatar = models.URLField(blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    preferred_language = models.CharField(max_length=2, choices=[('ar','Arabic'),('en','English'),('fr','French')], default='ar')
    timezone = models.CharField(max_length=80, default='Africa/Lagos')
    locale = models.CharField(max_length=30, default='ar')
    notification_preferences = models.JSONField(default=dict)
    theme = models.CharField(max_length=20, default='light')
''')
HEADER = '''from django.db import models
from django.conf import settings
from apps.common.models import Record, Scoped
'''
def fk(model, null=False, related='+'):
    return f"models.ForeignKey('{model}', on_delete=models.PROTECT, related_name='{related}'" + (', null=True, blank=True' if null else '') + ')'
def text(default=''):
    return 'models.TextField(blank=True)' if not default else f'models.TextField(default={default!r}, blank=True)'
def char(default='', length=200):
    return f'models.CharField(max_length={length}, default={default!r}, blank=True)'
def choice(values, default=None):
    vs=values.split(); return f'models.CharField(max_length=40, choices={[(v,v) for v in vs]!r}, default={default or vs[0]!r})'
def date(): return 'models.DateTimeField(null=True, blank=True)'
def json(): return 'models.JSONField(default=dict, blank=True)'
def integer(): return 'models.PositiveIntegerField(default=0)'
def decimal(): return 'models.DecimalField(max_digits=18, decimal_places=4, default=0)'
def model(name, fields, base='Scoped', constraints=None):
    s=f'\n\nclass {name}({base}):\n'
    s+=''.join(f'    {k} = {v}\n' for k,v in fields.items())
    if constraints:
        s+='    class Meta:\n        constraints = [\n'+''.join(f'            {c},\n' for c in constraints)+ '        ]\n'
    if 'title' in fields or 'name' in fields:
        s+='    def __str__(self): return self.'+('title' if 'title' in fields else 'name')+'\n'
    return s
def unique(fields,name): return f'models.UniqueConstraint(fields={fields!r}, name={name!r})'
data={a:HEADER for a in APPS if a not in ['common','accounts']}
def add(app,name,fields,base='Scoped',constraints=None): data[app]+=model(name,fields,base,constraints)
active='models.BooleanField(default=True)'
false='models.BooleanField(default=False)'
add('workspaces','Workspace',dict(name=char(),slug='models.SlugField(unique=True)',description=text(),active=active,created_by=fk('accounts.User',True),settings=json()),'Record')
add('workspaces','WorkspaceMembership',dict(workspace=fk('workspaces.Workspace'),user=fk('accounts.User'),role=choice('manager media_buyer editor reviewer requester viewer'),active=active,brand_restricted=false,brands="models.ManyToManyField('catalog.Brand', blank=True)",permission_overrides=json()),'Record',[unique(['workspace','user'],'workspace_member')])
add('catalog','Brand',dict(workspace=fk('workspaces.Workspace'),name=char(),slug='models.SlugField()',logo='models.URLField(blank=True)',active=active,metadata=json()),'Record',[unique(['workspace','slug'],'brand_slug')])
for n in ['Product','Campaign','Project','Tag','Taxonomy','NamingTemplate']:
    add('catalog',n,dict(name=char(),description=text(),active=active,metadata=json()))
add('catalog','Platform',dict(name=char(),slug='models.SlugField(unique=True)'), 'Record')
add('catalog','AttributeValue',dict(taxonomy=fk('catalog.Taxonomy'),creative=fk('creatives.Creative'),value=char()))
statuses='new assigned in_production ready_for_review changes_requested approved published refresh_requested'
add('requests_app','CreativeRequest',dict(code='models.CharField(max_length=40, unique=True)',title=char(),objective=text(),details=text(),priority=choice('normal high urgent low'),due_date=date(),status=choice(statuses),requester=fk('accounts.User'),owner=fk('accounts.User',True),product=fk('catalog.Product',True),campaign=fk('catalog.Campaign',True),platforms="models.ManyToManyField('catalog.Platform', blank=True)",completed_at=date(),published_at=date()))
add('requests_app','RequestDeliverable',dict(request=fk('requests_app.CreativeRequest',related='deliverables'),sequence='models.PositiveIntegerField()',title=char(),creative_type=choice('video image audio document'),platform=fk('catalog.Platform',True),aspect_ratio=char('9:16'),quantity='models.PositiveIntegerField(default=1)',duration_target=integer(),requirements=text(),assigned_editor=fk('accounts.User',True),due_date=date(),status=choice(statuses)),constraints=[unique(['request','sequence'],'deliverable_sequence'), 'models.CheckConstraint(condition=models.Q(quantity__gte=1), name="positive_quantity")'])
add('requests_app','RequestSourceMaterial',dict(request=fk('requests_app.CreativeRequest'),title=char(),kind=choice('note link file drive'),url='models.URLField(blank=True)',note=text(),storage_object=fk('storage.StorageObject',True)))
add('requests_app','SourceMaterialUsage',dict(source=fk('requests_app.RequestSourceMaterial'),version=fk('creatives.CreativeVersion')),constraints=[unique(['source','version'],'source_usage')])
add('creatives','Creative',dict(code='models.CharField(max_length=40, unique=True)',title=char(),description=text(),request=fk('requests_app.CreativeRequest',True),deliverable=fk('requests_app.RequestDeliverable',True),product=fk('catalog.Product',True),campaign=fk('catalog.Campaign',True),creative_type=choice('video image audio document'),owner=fk('accounts.User',True),status=choice(statuses),current_version=fk('creatives.CreativeVersion',True),approved_version=fk('creatives.CreativeVersion',True),outcome=char(),archived_at=date(),tags="models.ManyToManyField('catalog.Tag', blank=True)"))
add('creatives','CreativeVersion',dict(creative=fk('creatives.Creative',related='versions'),version_number='models.PositiveIntegerField()',label=char(),version_type=choice('original revision refresh'),editor=fk('accounts.User'),notes=text(),status=choice('draft submitted changes_requested approved published'),submitted_at=date(),approved_at=date(),published_at=date()),constraints=[unique(['creative','version_number'],'creative_version_number')])
add('creatives','CreativeComment',dict(creative=fk('creatives.Creative'),version=fk('creatives.CreativeVersion',True),author=fk('accounts.User'),text=text()))
add('creatives','CreativeFeedback',dict(version=fk('creatives.CreativeVersion'),author=fk('accounts.User'),text=text(),category=char(),resolved=false,resolved_at=date()))
add('creatives','CreativeRelationship',dict(parent=fk('creatives.Creative'),child=fk('creatives.Creative'),relationship=choice('variant refresh remake derivative localization'),hypothesis=text(),what_changed=text(),reason=text(),author=fk('accounts.User')),constraints=[unique(['parent','child','relationship'],'creative_relationship'), 'models.CheckConstraint(condition=~models.Q(parent=models.F("child")), name="no_self_lineage")'])
add('storage','StorageConnection',dict(name=char(),provider=choice('google_drive local'),account_email='models.EmailField(blank=True)',root_folder_id=char(),shared_drive_id=char(),credentials_encrypted=text(),scopes=json(),status=choice('disconnected connected error'),last_sync=date(),last_error=text(),change_token=text(),created_by=fk('accounts.User')))
add('storage','StorageObject',dict(connection=fk('storage.StorageConnection',True),provider=choice('local google_drive'),external_id=char(),filename=char(),mime_type=char(),size='models.PositiveBigIntegerField(default=0)',checksum=char(),width=integer(),height=integer(),duration=decimal(),local_path=char(length=500),parents='models.JSONField(default=list, blank=True)',active=active,metadata=json()),constraints=[unique(['connection','external_id'],'storage_external_identity')])
add('storage','DriveFolderMapping',dict(connection=fk('storage.StorageConnection'),entity_type=char(),entity_id='models.UUIDField()',folder_role=char(),drive_folder_id=char()),constraints=[unique(['connection','entity_type','entity_id','folder_role'],'drive_folder_identity')])
add('storage','CreativeFile',dict(creative=fk('creatives.Creative'),version=fk('creatives.CreativeVersion',True),storage_object=fk('storage.StorageObject'),role=choice('master source thumbnail subtitle export reference attachment'),active=active),constraints=[unique(['version','storage_object','role'],'creative_file_identity')])
add('storage','Upload',dict(connection=fk('storage.StorageConnection'),version=fk('creatives.CreativeVersion'),storage_object=fk('storage.StorageObject'),role=choice('master source thumbnail subtitle export reference attachment'),provider=choice('google_drive youtube'),status=choice('queued initializing uploading verifying complete failed cancelled'),idempotency_key='models.CharField(max_length=200, unique=True)',session_encrypted=text(),total_bytes='models.PositiveBigIntegerField(default=0)',uploaded_bytes='models.PositiveBigIntegerField(default=0)',attempts=integer(),last_error=text(),external_id=char(),privacy=choice('private unlisted public'),created_by=fk('accounts.User')))
add('storage','SyncRun',dict(connection=fk('storage.StorageConnection'),status=char('running'),object_count=integer(),error=text(),completed_at=date()))
add('storage','Clip',dict(source=fk('storage.StorageObject'),title=char(),start=decimal(),end=decimal(),description=text(),transcript=text(),tags="models.ManyToManyField('catalog.Tag', blank=True)",created_by=fk('accounts.User')),constraints=['models.CheckConstraint(condition=models.Q(end__gt=models.F("start")) & models.Q(start__gte=0), name="clip_interval")'])
add('storage','ClipUsage',dict(clip=fk('storage.Clip'),version=fk('creatives.CreativeVersion')),constraints=[unique(['clip','version'],'clip_usage')])
add('storage','ContentIndexEntry',dict(source=fk('storage.StorageObject'),version=fk('creatives.CreativeVersion',True),kind=choice('transcript ocr note'),machine_text=text(),corrected_text=text(),language=char('ar')))
add('integrations','AdConnection',dict(name=char(),provider=choice('meta tiktok google_ads'),account_id=char(),credentials_encrypted=text(),status=choice('disconnected connected error'),last_sync=date(),last_error=text(),created_by=fk('accounts.User')))
add('integrations','PublishJob',dict(creative=fk('creatives.Creative'),version=fk('creatives.CreativeVersion'),connection=fk('integrations.AdConnection'),provider=choice('meta tiktok google_ads'),state=choice('queued running waiting succeeded failed cancelled'),idempotency_key='models.CharField(max_length=200, unique=True)',requested_by=fk('accounts.User'),error=text(),receipt=json(),destination=json()))
add('integrations','PublishStep',dict(job=fk('integrations.PublishJob'),sequence='models.PositiveIntegerField()',operation=char(),status=choice('pending running succeeded uncertain failed'),fingerprint=char(),response=json(),external_id=char(),attempts=integer()),constraints=[unique(['job','operation'],'publish_operation')])
add('performance','Deployment',dict(title=char(),creative=fk('creatives.Creative'),version=fk('creatives.CreativeVersion'),provider=choice('manual meta tiktok youtube google_ads snapchat pinterest linkedin other'),connection=fk('integrations.AdConnection',True),external_account_id=char(),campaign_id=char(),adset_id=char(),ad_id=char(),destination_url='models.URLField(blank=True)',utm=json(),state=choice('draft paused active archived'),deployed_at=date(),last_sync=date()))
add('performance','PerformanceSnapshot',dict(deployment=fk('performance.Deployment'),provider=char('manual'),interval_start='models.DateTimeField()',interval_end='models.DateTimeField()',spend=decimal(),impressions=integer(),reach=integer(),clicks=integer(),link_clicks=integer(),conversions=integer(),purchases=integer(),revenue=decimal(),video_views=integer(),currency=char('USD',3),metrics=json()),constraints=[unique(['deployment','interval_start','interval_end'],'performance_window'), 'models.CheckConstraint(condition=models.Q(interval_end__gt=models.F("interval_start")), name="performance_interval")'])
add('performance','OutcomeHistory',dict(creative=fk('creatives.Creative'),outcome=choice('winner loser neutral fatigued refresh_requested'),reason=text(),actor=fk('accounts.User'),snapshot=fk('performance.PerformanceSnapshot',True)))
add('experiments','Experiment',dict(title=char(),hypothesis=text(),primary_kpi=choice('ctr roas cpa conversions'),secondary_kpi=char(),status=choice('draft running completed cancelled'),start_date=date(),end_date=date(),conclusion=text(),learning=text(),next_action=text(),winner=fk('experiments.ExperimentArm',True),limitations=text()))
add('experiments','ExperimentArm',dict(experiment=fk('experiments.Experiment',related='arms'),name=char(),control=false,creative=fk('creatives.Creative'),version=fk('creatives.CreativeVersion',True),deployment=fk('performance.Deployment',True)),constraints=[unique(['experiment','creative'],'experiment_creative')])
add('context_hub','ContextDocument',dict(title=char(),category=choice('guidelines facts allowed_claims forbidden_claims audience tone platform campaign'),current_version=fk('context_hub.ContextDocumentVersion',True),archived_at=date()))
add('context_hub','ContextDocumentVersion',dict(document=fk('context_hub.ContextDocument',related='versions'),version_number='models.PositiveIntegerField()',content=text(),status=choice('draft approved archived'),author=fk('accounts.User')),constraints=[unique(['document','version_number'],'context_version')])
add('context_hub','ContextCreativeLink',dict(document_version=fk('context_hub.ContextDocumentVersion'),creative=fk('creatives.Creative'),notes=text()))
add('context_hub','CreativeProposal',dict(title=char(),proposed_change=text(),rationale=text(),source=fk('creatives.Creative'),status=choice('proposed accepted rejected'),resulting_creative=fk('creatives.Creative',True)))
add('automations','AutomationRule',dict(name=char(),enabled=active,event=choice('ready_for_review approved fatigued overdue'),conditions=json(),action=choice('notify refresh_recommendation'),created_by=fk('accounts.User')))
add('automations','AutomationRun',dict(rule=fk('automations.AutomationRule'),event_id=char(),status=char('running'),error=text()),constraints=[unique(['rule','event_id'],'automation_once')])
add('automations','AutomationRunStep',dict(run=fk('automations.AutomationRun'),action=char(),status=char(),result=json()))
add('notifications','Notification',dict(user=fk('accounts.User'),kind=char(),title=char(),link=char(length=500),read_at=date(),dedupe_key='models.CharField(max_length=200, unique=True)'))
add('audit','AuditEvent',dict(actor=fk('accounts.User',True),action=char(),object_type=char(),object_id=char(),summary=json(),ip='models.GenericIPAddressField(null=True)',user_agent=char(length=500),correlation_id=char()))
add('audit','Activity',dict(actor=fk('accounts.User',True),action=char(),object_type=char(),object_id=char(),title=char()))
for app,content in data.items(): write(f'backend/apps/{app}/models.py',content)
print('Generated bounded Django models')

