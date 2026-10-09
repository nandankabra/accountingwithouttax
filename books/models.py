import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    mobile = models.CharField(max_length=20,blank=True)
    address = models.TextField(max_length=600,blank=True)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=80,blank=True)
    postcode = models.CharField(max_length=12,blank=True)
    profile_version = models.PositiveIntegerField(default=1)
    timezone = models.CharField(max_length=60, default='Asia/Kolkata')
    active_run = models.ForeignKey('CalculationRun', null=True, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name='Customer company'
        verbose_name_plural='Customer companies'

    def __str__(self):return self.name


class Account(models.Model):
    KINDS = [(x, x.title()) for x in ('cash', 'bank', 'customer', 'supplier', 'expense', 'income', 'asset', 'liability', 'equity')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=15, choices=KINDS)
    code = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'name'], name='account_name_unique'), models.UniqueConstraint(fields=['workspace', 'code'], name='account_code_unique'), models.CheckConstraint(condition=Q(kind__in=['cash','bank','customer','supplier','expense','income','asset','liability','equity']), name='valid_account_kind')]


class Item(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=20, default='pcs')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'name'], name='item_name_unique')]


class Voucher(models.Model):
    TYPES = [(x, label) for x, label in [('PAY','Payment'), ('REC','Receipt'), ('SAL','Sales'), ('PUR','Purchase'), ('CN','Credit note'), ('DN','Debit note'), ('REV','Reversal'), ('OPN','Opening balances')]]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    kind = models.CharField(max_length=3, choices=TYPES)
    sequence = models.PositiveIntegerField()
    date = models.DateField()
    version = models.PositiveIntegerField(default=1)
    data = models.JSONField()
    reverses = models.OneToOneField('self', null=True, on_delete=models.PROTECT, related_name='reversal')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def number(self):
        return f'{self.kind}-{self.sequence:06d}'

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'kind', 'sequence'], name='voucher_number_unique'), models.CheckConstraint(condition=Q(kind__in=['PAY','REC','SAL','PUR','CN','DN','REV','OPN']), name='valid_voucher_kind'), models.UniqueConstraint(fields=['workspace'],condition=Q(kind='OPN'),name='one_opening_per_workspace')]
        indexes = [models.Index(fields=['workspace', 'date', 'created_at'])]


class VoucherRevision(models.Model):
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT, related_name='revisions')
    version = models.PositiveIntegerField()
    data = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['voucher','version'], name='revision_unique')]


class CalculationRun(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=500)


class JournalEntry(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.PROTECT)
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    date = models.DateField()
    debit = models.DecimalField(max_digits=18, decimal_places=2)
    credit = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=['run','account','date'])]
        constraints = [models.CheckConstraint(condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)), name='one_journal_side')]


class StockMovement(models.Model):
    run = models.ForeignKey(CalculationRun, on_delete=models.PROTECT)
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT)
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    date = models.DateField()
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    value = models.DecimalField(max_digits=18, decimal_places=2)
    balance_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    balance_value = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=['run','item','date'])]
        constraints = [models.CheckConstraint(condition=Q(balance_quantity__gte=0, balance_value__gte=0), name='nonnegative_stock')]


class Mutation(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    voucher = models.ForeignKey(Voucher, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace','key'], name='idempotency_unique')]


class AuditEvent(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class AuthThrottle(models.Model):
    key = models.CharField(primary_key=True,max_length=64)
    window_start = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)


class SubscriptionPlan(models.Model):
    name=models.CharField(max_length=80,unique=True)
    price=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    duration_days=models.PositiveIntegerField(default=30)
    active=models.BooleanField(default=True)

    class Meta:
        constraints=[models.CheckConstraint(condition=Q(price__gte=0,duration_days__gte=1),name='valid_plan_terms')]

    def __str__(self):return self.name


class Subscription(models.Model):
    workspace=models.OneToOneField(Workspace,on_delete=models.PROTECT,related_name='subscription')
    plan=models.ForeignKey(SubscriptionPlan,null=True,blank=True,on_delete=models.PROTECT)
    status=models.CharField(max_length=12,choices=[('trial','Trial'),('active','Active'),('suspended','Suspended')],default='trial')
    starts_on=models.DateField()
    expires_on=models.DateField()
    notes=models.CharField(max_length=500,blank=True)
    requires_activation=models.BooleanField(default=False)
    key_digest=models.CharField(max_length=64,unique=True,null=True,blank=True,editable=False)
    key_enabled=models.BooleanField(default=False)
    key_version=models.PositiveIntegerField(default=0,editable=False)
    activated_at=models.DateTimeField(null=True,blank=True,editable=False)

    class Meta:
        constraints=[models.CheckConstraint(condition=Q(status__in=['trial','active','suspended']),name='valid_subscription_status'),models.CheckConstraint(condition=Q(expires_on__gte=models.F('starts_on')),name='valid_subscription_period')]

    def __str__(self):return self.workspace.name


class OfflineLicense(models.Model):
    """One signed, installation-bound licence for this standalone data file."""
    workspace = models.OneToOneField(Workspace, on_delete=models.PROTECT)
    signed_key = models.TextField()
    last_seen_date = models.DateField()
