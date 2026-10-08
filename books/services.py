import hashlib
import json
import uuid
from datetime import date
from django.db import transaction
from django.db.models import Max, Case, When, Value, IntegerField
from .models import Account, Item, Workspace, Voucher, VoucherRevision, CalculationRun, JournalEntry, StockMovement, Mutation, AuditEvent
from .engine import PostingError, normalize, normalize_opening, replay

SYSTEM_ACCOUNTS = [('inventory','Inventory','asset'), ('sales','Sales','income'), ('returns','Sales returns','income'), ('cogs','Cost of goods sold','expense'), ('rounding','Rounding adjustment','expense'), ('opening_equity','Opening balance equity','equity')]


@transaction.atomic
def create_workspace(owner, name):
    if not owner.email and '@' in owner.username:
        owner.email=owner.username
        owner.save(update_fields=['email'])
    ws = Workspace.objects.create(owner=owner, name=name)
    for code, label, kind in SYSTEM_ACCOUNTS:
        Account.objects.create(workspace=ws, name=label, kind=kind, code=code)
    for label, kind in [('Cash','cash'), ('Bank','bank'), ('General expenses','expense')]:
        Account.objects.create(workspace=ws, name=label, kind=kind)
    AuditEvent.objects.create(workspace=ws, actor=owner, action='workspace.created', details={'name': name})
    return ws


def serialize(v):
    return dict(id=str(v.id), number=v.number, kind=v.kind, date=v.date.isoformat(), version=v.version, data=v.data, reverses=str(v.reverses_id) if v.reverses_id else None)


@transaction.atomic
def mutate(owner, payload, key, voucher_id=None, reverse=False):
    try:
        key = uuid.UUID(str(key))
    except (ValueError, TypeError):
        raise PostingError('A valid idempotency key is required.')
    if not isinstance(payload, dict):
        raise PostingError('A JSON object is required.')
    fingerprint = hashlib.sha256(json.dumps([str(voucher_id), reverse, payload], sort_keys=True).encode()).hexdigest()
    # Committed mutation rows are immutable. Resolve confirmed retries without
    # waiting for an unrelated write in this workspace; recheck after locking
    # when the original request may still be in flight.
    prior = Mutation.objects.filter(workspace__owner=owner, key=key).first()
    if prior:
        if prior.fingerprint != fingerprint:
            raise PostingError('This submission key was already used for different data. Review before submitting again.', status=409)
        return {'id': str(prior.voucher_id), 'version': prior.version, 'duplicate': True}
    ws = Workspace.objects.select_for_update().get(owner=owner)
    prior = Mutation.objects.filter(workspace=ws, key=key).first()
    if prior:
        if prior.fingerprint != fingerprint:
            raise PostingError('This submission key was already used for different data. Review before submitting again.', status=409)
        return {'id': str(prior.voucher_id), 'version': prior.version, 'duplicate': True}
    reason = payload.get('reason','')
    if not isinstance(reason, str) or len(reason) > 500:
        raise PostingError('Use a reason of at most 500 characters.', 'reason')
    original = None
    if voucher_id:
        original = Voucher.objects.filter(workspace=ws, pk=voucher_id).first()
        if not original:
            raise PostingError('Voucher not found.', status=404)
        if type(payload.get('version')) is not int or payload.get('version') != original.version:
            raise PostingError('This voucher changed on another device. Refresh and review it.', status=409)
        if not reason.strip():
            raise PostingError('Explain the correction.', 'reason')
        if original.kind == 'REV' or Voucher.objects.filter(reverses=original).exists():
            raise PostingError('Reversed vouchers and reversal records cannot be edited or reversed again.', status=409)
    if reverse:
        if original.kind=='OPN':
            raise PostingError('Correct opening balances through their dedicated screen. An opening record cannot be reversed.')
        try:
            day = date.fromisoformat(payload.get('date',''))
        except (ValueError, TypeError):
            raise PostingError('Enter a valid reversal date.', 'date')
        if day < original.date:
            raise PostingError('Reversal date cannot precede the original.', 'date')
        kind, data = 'REV', dict(amount=original.data['amount'], narration=reason, lines=[], original=serialize(original))
    else:
        accounts = {str(a.id): {'kind': a.kind, 'system': bool(a.code)} for a in Account.objects.filter(workspace=ws)}
        items = {str(i.id) for i in Item.objects.filter(workspace=ws)}
        if payload.get('kind')=='OPN':
            if not original and Voucher.objects.filter(workspace=ws,kind='OPN').exists():
                raise PostingError('Opening balances already exist. Refresh and correct the existing record.', status=409)
            data = normalize_opening(payload, accounts, items)
        else:
            data = normalize(payload, accounts, items)
        day, kind = date.fromisoformat(data['date']), data['kind']
        if original and kind != original.kind:
            raise PostingError('A posted voucher type cannot be changed.', 'kind')
    if original and not reverse:
        v = original
        v.version += 1
        v.data, v.date = data, day
        v.save(update_fields=['version','data','date'])
        action = 'voucher.edited'
    else:
        sequence = (Voucher.objects.filter(workspace=ws, kind=kind).aggregate(n=Max('sequence'))['n'] or 0) + 1
        v = Voucher.objects.create(workspace=ws, kind=kind, date=day, sequence=sequence, data=data, reverses=original if reverse else None)
        action = 'voucher.reversed' if reverse else 'voucher.posted'
    VoucherRevision.objects.create(voucher=v, version=v.version, data=serialize(v), actor=owner, reason=reason.strip() or 'Initial posting')
    system = {a.code: str(a.id) for a in Account.objects.filter(workspace=ws, code__isnull=False)}
    ordered = [serialize(row) for row in Voucher.objects.filter(workspace=ws).annotate(opening_order=Case(When(kind='OPN',then=Value(0)),default=Value(1),output_field=IntegerField())).order_by('date','opening_order','created_at','id')]
    journal, stock = replay(ordered, system)
    run = CalculationRun.objects.create(workspace=ws, reason=f'{action}: {v.number}')
    JournalEntry.objects.bulk_create([JournalEntry(run=run, voucher_id=r['voucher'], account_id=r['account'], date=r['date'], debit=r['debit'], credit=r['credit']) for r in journal], batch_size=500)
    StockMovement.objects.bulk_create([StockMovement(run=run, voucher_id=r['voucher'], item_id=r['item'], date=r['date'], quantity=r['quantity'], value=r['value'], balance_quantity=r['balance_quantity'], balance_value=r['balance_value']) for r in stock], batch_size=500)
    ws.active_run = run
    ws.save(update_fields=['active_run'])
    Mutation.objects.create(workspace=ws, key=key, fingerprint=fingerprint, voucher=v, version=v.version)
    AuditEvent.objects.create(workspace=ws, actor=owner, action=action, details={'voucher': str(v.id), 'number': v.number, 'version': v.version, 'reason': reason, 'run': run.id})
    return {'id': str(v.id), 'version': v.version, 'number': v.number, 'duplicate': False}
