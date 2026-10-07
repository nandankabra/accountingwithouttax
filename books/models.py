import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=60, default='Asia/Kolkata')
    active_run = models.ForeignKey('CalculationRun', null=True, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)


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
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
