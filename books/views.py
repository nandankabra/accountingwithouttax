import csv
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from functools import wraps
from types import SimpleNamespace
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction, connection
from django.db.models import Sum, Q, DecimalField
from django.db.models.functions import Cast
from django.db.models.fields.json import KeyTextTransform
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.conf import settings
from .subscriptions import ensure_can_write,access
from .forms import SignupForm, LoginForm
from .models import Workspace, Account, Item, Voucher, JournalEntry, StockMovement, AuditEvent
from .engine import PostingError
from .services import create_workspace, mutate, serialize
from .security import login_allowed,clear_login_limit


def audit_auth(request, action, user):
    ws = Workspace.objects.filter(owner=user).first()
    if ws:
        AuditEvent.objects.create(workspace=ws, actor=user if request.user.is_authenticated else None, action=action, details={'account':user.username})


def auth_page(request, signup=False):
    if getattr(settings, 'LOCAL_DESKTOP', False):
        return redirect('/' if request.user.is_authenticated else '/activate/')
    if signup and not settings.ALLOW_SELF_SIGNUP:return HttpResponse('Accounts are created by your service provider. Contact them for access.',status=403)
    if request.user.is_authenticated:
        return redirect('/')
    form = SignupForm(request.POST or None) if signup else LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        name = request.POST.get('username','').lower()
        if not login_allowed(request,name):
            form.add_error(None, 'Too many attempts. Please wait 15 minutes before trying again.')
        elif form.is_valid():
            if signup:
                try:
                    with transaction.atomic():
                        user = form.save()
                        user.email=user.username
                        user.save(update_fields=['email'])
                        create_workspace(user, form.cleaned_data['business'])
                except IntegrityError:
                    form.add_error('username', 'This email is already registered.')
                    return render(request, 'books/auth.html', {'form': form, 'signup': signup})
            else:
                user = form.get_user()
            login(request, user)
            audit_auth(request, 'auth.login', user)
            clear_login_limit(name)
            return redirect('/')
        else:
            user = User.objects.filter(username=name).first()
            if user:
                audit_auth(request, 'auth.failed', user)
    return render(request, 'books/auth.html', {'form': form, 'signup': signup})


@require_POST
def logout_page(request):
    if request.user.is_authenticated:
        audit_auth(request, 'auth.logout', request.user)
    logout(request)
    return redirect('/login/')


@login_required
def home(request):
    if request.user.is_superuser:return redirect('/admin/')
    if request.user.workspace.subscription.requires_activation and not access(request.user.workspace)['activated']:return redirect('/activate/')
    return render(request, 'books/app.html', {'workspace': request.user.workspace})


def api(methods=('GET',)):
    def decorate(fn):
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Your session has expired. Sign in again; your draft is saved in this browser.'}, status=401)
            if request.method not in methods:
                return JsonResponse({'error': 'Method not allowed.'}, status=405)
            try:
                request.workspace = Workspace.objects.get(owner=request.user)
                if request.method in ('POST','PUT'):
                    request.payload = json.loads(request.body)
                    if not isinstance(request.payload, dict):
                        raise PostingError('Send a JSON object.')
                return fn(request, *args, **kwargs)
            except Workspace.DoesNotExist:
                return JsonResponse({'error':'Use product administration to manage customers.'},status=403)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({'error': 'Invalid JSON.', 'reference_id': request.reference_id}, status=400)
            except PostingError as exc:
                return JsonResponse({'error': str(exc), 'field': exc.field, 'reference_id': request.reference_id}, status=exc.status)
            except IntegrityError:
                return JsonResponse({'error': 'A record with this name already exists or the request conflicts with an existing record.', 'reference_id': request.reference_id}, status=409)
        return wrapped
    return decorate


def period(request):
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get('start') or today.replace(day=1).isoformat())
        end = date.fromisoformat(request.GET.get('end') or today.isoformat())
    except ValueError:
        raise PostingError('Choose a valid date range.')
    if start > end:
        raise PostingError('Start date must be before or equal to end date.')
    return start, end


def page_of(request, query, serializer):
    try:
        number = int(request.GET.get('page', 1))
    except ValueError:
        raise PostingError('Invalid page number.')
    pager = Paginator(query, 25)
    page = pager.get_page(number)
    return {'rows': [serializer(r) for r in page], 'page': page.number, 'pages': pager.num_pages, 'count': pager.count}


def owned_id(value, model, workspace, label):
    try:
        key = uuid.UUID(str(value))
    except ValueError:
        raise PostingError(f'Select a valid {label}.')
    row = model.objects.filter(workspace=workspace, pk=key).first()
    if not row:
        raise PostingError(f'{label.title()} not found.', status=404)
    return row


@api()
def bootstrap(request):
    ws = request.workspace
    accounts=Account.objects.filter(workspace=ws).order_by('name','id')
    items=Item.objects.filter(workspace=ws).order_by('name','id')
    return JsonResponse({'workspace': {'id': str(ws.id), 'name': ws.name, 'timezone': ws.timezone}, 'user': request.user.username, 'today': timezone.localdate().isoformat(), 'accounts': list(accounts.values('id','name','kind','code')[:25]), 'items': list(items.values('id','name','unit')[:25]), 'subscription':access(ws),'default_cash':accounts.filter(kind='cash').values('id','name','kind','code').first()})


def master_list(request,collection):
    if collection not in ('accounts','items'):
        raise PostingError('Not found.',status=404)
    model=Account if collection=='accounts' else Item
    query=model.objects.filter(workspace=request.workspace)
    fields=['id','name','kind','code'] if collection=='accounts' else ['id','name','unit']
    if 'ids' in request.GET:
        values=request.GET['ids'].split(',')
        if len(values)>200:raise PostingError('Look up at most 200 masters at once.')
        try:keys=[uuid.UUID(value) for value in values]
        except ValueError:raise PostingError('Use valid master identifiers.')
        return JsonResponse({'rows':list(query.filter(pk__in=keys).order_by('name','id').values(*fields))})
    search=request.GET.get('q','').strip()
    if len(search)>120:raise PostingError('Search must be at most 120 characters.','q')
    if search:query=query.filter(name__icontains=search)
    kinds=request.GET.get('kinds','')
    if kinds and collection=='accounts':
        kinds=kinds.split(',')
        if any(kind not in dict(Account.KINDS) for kind in kinds):raise PostingError('Select valid account groups.')
        query=query.filter(kind__in=kinds)
    if collection=='accounts' and request.GET.get('non_system')=='1':query=query.filter(code__isnull=True)
    sort=request.GET.get('sort','name')
    if sort not in ('name','name-desc'):raise PostingError('Choose a valid sort order.','sort')
    query=query.order_by('name' if sort=='name' else '-name','id')
    return JsonResponse(page_of(request,query,lambda row:{key:str(getattr(row,key)) if key=='id' else getattr(row,key) for key in fields}))


@api(('GET','POST'))
def master_create(request, collection):
    if request.method=='GET':return master_list(request,collection)
    if collection not in ('accounts','items'):
        raise PostingError('Not found.', status=404)
    data = request.payload
    name = data.get('name')
    if not isinstance(name,str) or not name.strip() or len(name.strip()) > 120:
        raise PostingError('Enter a name with 1 to 120 characters.', 'name')
    with transaction.atomic():
        ws = Workspace.objects.select_for_update().get(pk=request.workspace.pk)
        ensure_can_write(ws)
        if collection == 'accounts':
            kind = data.get('kind')
            if kind not in dict(Account.KINDS):
                raise PostingError('Select a valid account group.', 'kind')
            row = Account.objects.create(workspace=ws, name=name.strip(), kind=kind)
        else:
            unit = data.get('unit','pcs')
            if not isinstance(unit,str) or not unit.strip() or len(unit) > 20:
                raise PostingError('Enter a unit with 1 to 20 characters.', 'unit')
            row = Item.objects.create(workspace=ws, name=name.strip(), unit=unit.strip())
        AuditEvent.objects.create(workspace=ws, actor=request.user, action=f'{collection}.created', details={'id':str(row.id),'name':row.name})
    return JsonResponse({'id':str(row.id)}, status=201)


@api()
def dashboard(request):
    start,end = period(request)
    ws = request.workspace
    query = Voucher.objects.filter(workspace=ws, date__range=(start,end))
    amount = Cast(KeyTextTransform('amount', 'data'), DecimalField(max_digits=18, decimal_places=2))
    totals = {k: Decimal('0') for k in ('PAY','REC','SAL','PUR','CN','DN')}
    if connection.vendor == 'sqlite':
        for row in query.exclude(kind='OPN').values('kind', 'data', 'reverses__kind').iterator():
            if row['kind'] == 'REV':
                totals[row['reverses__kind']] -= Decimal(row['data']['amount'])
            else:
                totals[row['kind']] += Decimal(row['data']['amount'])
    else:
        for row in query.exclude(kind__in=['REV','OPN']).values('kind').annotate(total=Sum(amount)):
            totals[row['kind']] = row['total']
        for row in query.filter(kind='REV').values('reverses__kind').annotate(total=Sum(amount)):
            totals[row['reverses__kind']] -= row['total']
    entries = JournalEntry.objects.filter(run_id=ws.active_run_id, date__lte=end)
    def balance(kinds):
        row = decimal_totals(entries.filter(account__kind__in=kinds), d='debit', c='credit')
        return (row['d'] or 0) - (row['c'] or 0)
    stock = decimal_totals(StockMovement.objects.filter(run_id=ws.active_run_id, date__lte=end), value='value')['value'] or 0
    return JsonResponse({'totals':totals,'cash':balance(['cash','bank']), 'receivable':balance(['customer']), 'payable':-balance(['supplier']), 'stock_value':stock, 'voucher_count':query.count(), 'start':start,'end':end,'refreshed_at':timezone.now(), 'recent':[serialize(v) for v in query.order_by('-date','-created_at')[:8]]})


@api(('GET','POST'))
def vouchers(request):
    if request.method == 'POST':
        return JsonResponse(mutate(request.user, request.payload, request.headers.get('Idempotency-Key')), status=201)
    return JsonResponse(page_of(request, voucher_query(request), serialize))


def voucher_query(request):
    start,end = period(request)
    query = Voucher.objects.filter(workspace=request.workspace, date__range=(start,end))
    kind = request.GET.get('kind')
    if kind:
        query = query.filter(kind=kind)
    search = request.GET.get('q','').strip()[:120]
    if search:
        if '-' in search and search.rsplit('-',1)[-1].isdigit():
            prefix,seq = search.rsplit('-',1)
            query = query.filter(kind=prefix.upper(), sequence=int(seq))
        else:
            query = query.filter(data__narration__icontains=search)
    order = 'date' if request.GET.get('sort') == 'oldest' else '-date'
    return query.order_by(order, 'created_at')


@api(('GET','PUT','POST'))
def voucher_detail(request, voucher_id, action=None):
    if request.method in ('PUT','POST'):
        if (request.method == 'POST') != (action == 'reverse'):
            raise PostingError('Method not allowed.', status=405)
        return JsonResponse(mutate(request.user, request.payload, request.headers.get('Idempotency-Key'), voucher_id, reverse=action=='reverse'))
    v = owned_id(voucher_id, Voucher, request.workspace, 'voucher')
    result = serialize(v)
    result['reversed'] = Voucher.objects.filter(reverses=v).exists()
    result['journal'] = list(JournalEntry.objects.filter(run_id=request.workspace.active_run_id,voucher=v).values('account__name','debit','credit'))
    return JsonResponse(result)


@api()
def opening(request):
    voucher=Voucher.objects.filter(workspace=request.workspace,kind='OPN').first()
    return JsonResponse({'voucher':serialize(voucher) if voucher else None})


def decimal_totals(query, **fields):
    if connection.vendor != 'sqlite':
        return query.aggregate(**{name: Sum(field) for name, field in fields.items()})
    # Python Decimal also avoids overflow of SQLite's 64-bit SUM accumulator.
    totals = {name: Decimal('0') for name in fields}
    for row in query.values_list(*fields.values()).iterator():
        for name, value in zip(fields, row):
            totals[name] += value
    return totals


def ledger_query(request):
    start,end = period(request)
    query = JournalEntry.objects.filter(run_id=request.workspace.active_run_id)
    if request.GET.get('account')=='cash-bank':
        account=SimpleNamespace(id='cash-bank',name='Cash & bank (combined)')
        query=query.filter(account__kind__in=['cash','bank'])
    else:
        account=owned_id(request.GET.get('account'),Account,request.workspace,'account')
        query=query.filter(account=account)
    opening = decimal_totals(query.filter(date__lt=start), d='debit', c='credit')
    opening = (opening['d'] or 0) - (opening['c'] or 0)
    return account,start,end,query,opening


@api()
def ledger(request):
    account,start,end,query,opening = ledger_query(request)
    rows = query.filter(date__range=(start,end)).select_related('voucher','account').order_by('date','id')
    totals = decimal_totals(rows, d='debit', c='credit')
    result = page_of(request, book_rows(request,rows), lambda r: {'id':r.id,'date':r.date,'voucher':str(r.voucher_id),'number':r.voucher.number,'account':r.account.name,'debit':r.debit,'credit':r.credit})
    result.update(opening=opening, debit=totals['d'] or 0, credit=totals['c'] or 0, closing=opening+(totals['d'] or 0)-(totals['c'] or 0), account=account.name)
    return JsonResponse(result)


@api()
def inventory(request):
    item,start,end,query,opening,closing=inventory_query(request)
    result = page_of(request, book_rows(request,query.filter(date__range=(start,end))).select_related('voucher'), lambda r: {'date':r.date,'voucher':str(r.voucher_id),'number':r.voucher.number,'quantity':r.quantity,'value':r.value,'balance_quantity':r.balance_quantity,'balance_value':r.balance_value})
    result.update(opening=opening,closing=closing,item=item.name,unit=item.unit)
    return JsonResponse(result)


def book_rows(request,query):
    """Filter visible movements without changing the accounting-period totals."""
    search=request.GET.get('q','').strip()
    if len(search)>120:raise PostingError('Search must be at most 120 characters.','q')
    if search:
        parts=search.rsplit('-',1)
        if len(parts)==2 and parts[0].upper() in dict(Voucher.TYPES) and parts[1].isdigit():
            query=query.filter(voucher__kind=parts[0].upper(),voucher__sequence=int(parts[1]))
        else:
            query=query.filter(Q(voucher__data__narration__icontains=search)|Q(voucher__kind__icontains=search))
    direction=request.GET.get('direction','')
    allowed={'debit':'debit__gt','credit':'credit__gt'} if query.model is JournalEntry else {'inward':'quantity__gt','outward':'quantity__lt'}
    if direction:
        if direction not in allowed:raise PostingError('Choose a valid movement direction.','direction')
        query=query.filter(**{allowed[direction]:0})
    sort=request.GET.get('sort','oldest')
    if sort not in ('oldest','newest'):raise PostingError('Choose a valid sort order.','sort')
    return query.order_by(*(['date','id'] if sort=='oldest' else ['-date','-id']))


def inventory_query(request):
    item = owned_id(request.GET.get('item'), Item, request.workspace, 'item')
    start,end = period(request)
    query = StockMovement.objects.filter(run_id=request.workspace.active_run_id,item=item)
    opening = decimal_totals(query.filter(date__lt=start), quantity='quantity', value='value')
    closing = decimal_totals(query.filter(date__lte=end), quantity='quantity', value='value')
    return item,start,end,query,{k:v or 0 for k,v in opening.items()},{k:v or 0 for k,v in closing.items()}


@api()
def audit(request):
    return JsonResponse(page_of(request, AuditEvent.objects.filter(workspace=request.workspace).select_related('actor').order_by('-id'), lambda r: {'action':r.action,'details':r.details,'at':r.created_at,'actor':r.actor.username if r.actor else 'Unauthenticated request'}))


def csv_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value


def csv_report(request,filename,start,end):
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="{filename}.csv"'
    response.write('\ufeff')
    writer=csv.writer(response)
    writer.writerow(['Organisation',csv_safe(request.workspace.name),'Generated by',csv_safe(request.user.username)])
    writer.writerow(['Generated at',timezone.now().isoformat(),'Timezone',request.workspace.timezone])
    writer.writerow(['Period',str(start),str(end)])
    return response,writer


@api()
def ledger_export(request):
    account,start,end,query,opening = ledger_query(request)
    rows = query.filter(date__range=(start,end)).select_related('voucher','account').order_by('date','id')
    if rows.count() > 5000:
        raise PostingError('Choose a smaller date range: exports are limited to 5,000 entries.')
    selected_ids=set(book_rows(request,rows).values_list('id',flat=True))
    records=[]
    balance=opening
    for row in rows:
        balance+=row.debit-row.credit
        if row.id in selected_ids:records.append((row,balance))
    if request.GET.get('sort')=='newest':records.reverse()
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="ledger.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Organisation',csv_safe(request.workspace.name),'Generated by',csv_safe(request.user.username)])
    writer.writerow(['Generated at',timezone.now().isoformat(),'Timezone',request.workspace.timezone])
    writer.writerow(['Period',str(start),str(end),'Account',csv_safe(account.name)])
    writer.writerow(['Opening (debit positive)',str(opening)])
    writer.writerow(['Closing for full period (debit positive)',str(balance)])
    writer.writerow(['Search',csv_safe(request.GET.get('q','')),'Direction',csv_safe(request.GET.get('direction','All')),'Sort',csv_safe(request.GET.get('sort','oldest'))])
    writer.writerow(['Date','Voucher ID','Voucher number','Account ID','Account','Debit INR','Credit INR','Balance INR'])
    for r,balance in records:
        writer.writerow([r.date,str(r.voucher_id),r.voucher.number,str(r.account_id),csv_safe(r.account.name),str(r.debit),str(r.credit),str(balance)])
    AuditEvent.objects.create(workspace=request.workspace,actor=request.user,action='ledger.exported',details={'account':str(account.id),'start':str(start),'end':str(end),'q':request.GET.get('q',''),'direction':request.GET.get('direction',''),'sort':request.GET.get('sort','oldest')})
    return response


@api()
def inventory_export(request):
    item,start,end,query,opening,closing=inventory_query(request)
    rows=book_rows(request,query.filter(date__range=(start,end))).select_related('voucher')
    if rows.count()>5000:
        raise PostingError('Choose a smaller date range: exports are limited to 5,000 stock movements.')
    response,writer=csv_report(request,'inventory',start,end)
    writer.writerow(['Item ID',str(item.id),'Item',csv_safe(item.name),'Unit',csv_safe(item.unit)])
    writer.writerow(['Opening quantity',str(opening['quantity']),'Opening value INR',str(opening['value'])])
    writer.writerow(['Closing quantity',str(closing['quantity']),'Closing value INR',str(closing['value'])])
    writer.writerow(['Search',csv_safe(request.GET.get('q','')),'Direction',csv_safe(request.GET.get('direction','All')),'Sort',csv_safe(request.GET.get('sort','oldest'))])
    writer.writerow(['Date','Voucher ID','Voucher number','Type','Quantity inward','Quantity outward','Value movement INR','Quantity balance','Value balance INR'])
    for row in rows.iterator(chunk_size=500):
        writer.writerow([row.date,str(row.voucher_id),row.voucher.number,row.voucher.kind,str(max(row.quantity,0)),str(max(-row.quantity,0)),str(row.value),str(row.balance_quantity),str(row.balance_value)])
    AuditEvent.objects.create(workspace=request.workspace,actor=request.user,action='inventory.exported',details={'item':str(item.id),'start':str(start),'end':str(end),'q':request.GET.get('q',''),'direction':request.GET.get('direction',''),'sort':request.GET.get('sort','oldest')})
    return response


@api()
def voucher_export(request):
    start,end=period(request)
    rows=voucher_query(request).select_related('reversal')
    # Bound both voucher count and expanded item/account rows before generation.
    if rows.count()>5000:
        raise PostingError('Choose a smaller date range: exports are limited to 5,000 rows.')
    records=list(rows)
    if sum(max(1,len(v.data.get('lines',[]))+len(v.data.get('balances',[]))) for v in records)>5000:
        raise PostingError('Choose a smaller date range: item-wise exports are limited to 5,000 rows.')
    accounts={str(a.id):a.name for a in Account.objects.filter(workspace=request.workspace)}
    items={str(i.id):i.name for i in Item.objects.filter(workspace=request.workspace)}
    response,writer=csv_report(request,'vouchers',start,end)
    writer.writerow(['Type filter',csv_safe(request.GET.get('kind','All')),'Search',csv_safe(request.GET.get('q',''))])
    writer.writerow(['Voucher ID','Number','Date','Type','Version','Status','Voucher total INR','Row type','Account ID','Account','Cash/bank ID','Cash/bank','Item ID','Item','Quantity','Rate INR','Line amount INR','Balance side','Reference voucher ID','Reverses voucher ID','Narration'])
    for v in records:
        d=v.data
        status='reversed' if hasattr(v,'reversal') else 'posted'
        lines=[('item',l) for l in d.get('lines',[])]+[('balance',l) for l in d.get('balances',[])] or [('voucher',{})]
        for row_type,line in lines:
            account=line.get('account',d.get('account',''))
            item=line.get('item','')
            cash=d.get('cash_account','')
            writer.writerow([str(v.id),v.number,str(v.date),v.kind,v.version,status,d['amount'],row_type,account,csv_safe(accounts.get(account,'')),cash,csv_safe(accounts.get(cash,'')),item,csv_safe(items.get(item,'')),line.get('quantity',''),line.get('rate',''),line.get('amount',d['amount']),line.get('side',''),d.get('reference',''),str(v.reverses_id or ''),csv_safe(d.get('narration',''))])
    AuditEvent.objects.create(workspace=request.workspace,actor=request.user,action='vouchers.exported',details={'start':str(start),'end':str(end),'kind':request.GET.get('kind',''),'vouchers':len(records)})
    return response
