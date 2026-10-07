"""Deterministic perpetual-inventory replay. No database or HTTP dependencies."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date

ZERO = Decimal('0')
PAISE = Decimal('.01')


class PostingError(ValueError):
    def __init__(self, message, field='__all__', status=400):
        super().__init__(message)
        self.field, self.status = field, status


def money(value):
    return Decimal(value).quantize(PAISE, rounding=ROUND_HALF_UP)


def decimal_input(value, field, places=2, allow_zero=False):
    # JSON numbers are deliberately rejected: clients must send exact decimal strings.
    if not isinstance(value, str) or len(value) > 30:
        raise PostingError('Enter a decimal value as text.', field)
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise PostingError('Enter a valid number.', field)
    if not result.is_finite() or result < 0 or (result == 0 and not allow_zero) or result >= Decimal('1000000000'):
        raise PostingError('Enter a valid non-negative number below 1,000,000,000.' if allow_zero else 'Enter a number greater than zero and below 1,000,000,000.', field)
    if result.as_tuple().exponent < -places:
        raise PostingError(f'Use at most {places} decimal places.', field)
    return result


def verify_total(value, total):
    try:
        expected=Decimal(value) if isinstance(value,str) and len(value)<=30 else None
    except InvalidOperation:
        expected=None
    if expected is None or not expected.is_finite() or expected!=total:
        raise PostingError('The submitted total differs from the server total. Review the voucher.', 'expected_total')


def normalize(payload, accounts, items):
    if not isinstance(payload, dict):
        raise PostingError('A voucher object is required.')
    kind = payload.get('kind')
    if kind not in ('PAY','REC','SAL','PUR','CN','DN'):
        raise PostingError('Choose a supported voucher type.', 'kind')
    try:
        day = date.fromisoformat(payload.get('date', ''))
    except (ValueError, TypeError):
        raise PostingError('Enter a valid date.', 'date')
    narration = payload.get('narration', '')
    if not isinstance(narration, str) or len(narration) > 500:
        raise PostingError('Narration must be at most 500 characters.', 'narration')
    party = payload.get('account')
    if not isinstance(party, str) or party not in accounts or accounts[party].get('system'):
        raise PostingError('Choose an account in this workspace.', 'account')
    out = dict(kind=kind, date=day.isoformat(), narration=narration.strip(), account=party)
    if kind in ('PAY','REC'):
        cash = payload.get('cash_account')
        if not isinstance(cash, str) or cash not in accounts or accounts[cash]['kind'] not in ('cash','bank') or cash == party:
            raise PostingError('Choose a different cash or bank account.', 'cash_account')
        total = money(decimal_input(payload.get('amount'), 'amount'))
        out.update(cash_account=cash, amount=str(total), lines=[])
    else:
        allowed = ('customer','cash','bank') if kind in ('SAL','CN') else ('supplier','cash','bank')
        if accounts[party]['kind'] not in allowed:
            raise PostingError('Choose a customer for sales/credit notes or supplier for purchases/debit notes; cash/bank is also allowed.', 'account')
        lines = payload.get('lines')
        if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
            raise PostingError('Add between 1 and 100 item lines.', 'lines')
        clean, seen = [], set()
        for i, line in enumerate(lines):
            if not isinstance(line, dict):
                raise PostingError('Each item line must be an object.', 'lines')
            item = line.get('item')
            if not isinstance(item, str) or item not in items or item in seen:
                raise PostingError(f'Line {i+1}: choose a unique item in this workspace.', 'lines')
            seen.add(item)
            qty = decimal_input(line.get('quantity'), 'lines', 3)
            rate = decimal_input(line.get('rate'), 'lines', 2)
            amount = money(qty * rate)
            if amount <= 0 or amount >= Decimal('1000000000000'):
                raise PostingError('Each line must be between ₹0.01 and ₹1 trillion.', 'lines')
            clean.append(dict(item=item, quantity=str(qty), rate=str(rate), amount=str(amount)))
        total = sum((Decimal(l['amount']) for l in clean), ZERO)
        out.update(lines=clean, amount=str(total))
        if kind in ('CN','DN'):
            ref = payload.get('reference')
            if not isinstance(ref, str) or not ref:
                raise PostingError('Select the original sale or purchase.', 'reference')
            out['reference'] = ref
    if total >= Decimal('1000000000000'):
        raise PostingError('Voucher total must be below ₹1 trillion.', 'amount')
    verify_total(payload.get('expected_total'),total)
    return out


def normalize_opening(payload, accounts, items):
    """Financial balances plus physical opening stock; equity offsets the net."""
    try:
        day = date.fromisoformat(payload.get('date',''))
    except (TypeError, ValueError):
        raise PostingError('Enter a valid opening date.', 'date')
    balances, lines = payload.get('balances'), payload.get('lines')
    if not isinstance(balances,list) or not isinstance(lines,list) or len(balances)+len(lines)>200:
        raise PostingError('Provide account and item lists, with at most 200 rows in total.')
    clean_balances, clean_lines, seen_accounts, seen_items = [], [], set(), set()
    debit, credit = ZERO, ZERO
    for row in balances:
        if not isinstance(row,dict):
            raise PostingError('Each balance must be an object.', 'balances')
        account = row.get('account')
        if not isinstance(account,str) or account not in accounts or accounts[account].get('system') or account in seen_accounts:
            raise PostingError('Choose each non-system account at most once from your workspace.', 'balances')
        if row.get('side') not in ('debit','credit'):
            raise PostingError('Choose debit or credit for each account.', 'balances')
        amount = money(decimal_input(row.get('amount'),'balances'))
        seen_accounts.add(account)
        clean_balances.append(dict(account=account,side=row['side'],amount=str(amount)))
        if row['side']=='debit':debit+=amount
        else:credit+=amount
    for row in lines:
        if not isinstance(row,dict):
            raise PostingError('Each stock line must be an object.', 'lines')
        item = row.get('item')
        if not isinstance(item,str) or item not in items or item in seen_items:
            raise PostingError('Choose each item at most once from your workspace.', 'lines')
        qty = decimal_input(row.get('quantity'),'lines',3)
        value = money(decimal_input(row.get('amount'),'lines',allow_zero=True))
        seen_items.add(item)
        clean_lines.append(dict(item=item,quantity=str(qty),amount=str(value)))
        debit+=value
    total=max(debit,credit)
    if total>=Decimal('1000000000000'):
        raise PostingError('Opening total must be below ₹1 trillion.', 'expected_total')
    verify_total(payload.get('expected_total'),total)
    return dict(kind='OPN',date=day.isoformat(),balances=clean_balances,lines=clean_lines,amount=str(money(total)),narration='Opening balances',equity_offset=str(money(credit-debit)))


def replay(vouchers, system):
    """Ordered current revisions -> immutable journal and stock snapshot.

    Stock value is in paise; full depletion takes the residual cost. Returns use
    cumulative proportional source cost, so multiple partial returns add exactly.
    """
    stock = defaultdict(lambda: [ZERO, ZERO])
    journal, movements, sources, reversed_ids = [], [], {}, set()
    returned = defaultdict(lambda: ZERO)
    returned_cost = defaultdict(lambda: ZERO)
    returned_amount = defaultdict(lambda: ZERO)
    openings=[v for v in vouchers if v['kind']=='OPN']
    if len(openings)>1:
        raise PostingError('Only one opening-balance record is allowed.')
    if openings and any(v['date']<openings[0]['date'] for v in vouchers):
        raise PostingError('Opening date must be on or before every other voucher. Posting before the opening date is not allowed.', 'date')

    def entry(v, account, debit=ZERO, credit=ZERO):
        if debit or credit:
            row = dict(voucher=v['id'], account=account, date=v['date'], debit=money(debit), credit=money(credit))
            journal.append(row)
            return row

    def move(v, item, qty, value):
        q, val = stock[item]
        q, val = q + qty, money(val + value)
        if q < 0:
            raise PostingError(f"{v['number']}: insufficient stock. This change would make an item negative.", 'lines')
        if val < 0 or (q == 0 and val != 0):
            raise PostingError(f"{v['number']}: this return/reversal would leave inconsistent stock value. Correct subsequent stock transactions first.", 'lines')
        stock[item] = [q, val]
        row = dict(voucher=v['id'], item=item, date=v['date'], quantity=qty, value=value, balance_quantity=q, balance_value=val)
        movements.append(row)
        return row

    for v in vouchers:
        start_j, start_m = len(journal), len(movements)
        d, kind = v['data'], v['kind']
        costs = {}
        if kind == 'REV':
            ref = v['reverses']
            if ref not in sources or ref in reversed_ids:
                raise PostingError('A reversal must follow an unreversed original voucher.', 'date')
            original = sources[ref]
            if original['voucher']['kind'] == 'REV':
                raise PostingError('A reversal cannot itself be reversed.')
            if any(q > 0 for (source, _), q in returned.items() if source == ref):
                raise PostingError('Reverse the linked returns before reversing the original voucher.')
            for row in original['journal']:
                entry(v, row['account'], row['credit'], row['debit'])
            for row in original['movements']:
                move(v, row['item'], -row['quantity'], -row['value'])
            od = original['voucher']['data']
            if original['voucher']['kind'] in ('CN','DN'):
                for line in od['lines']:
                    key=(od['reference'], line['item'])
                    returned[key] -= Decimal(line['quantity'])
                    returned_cost[key] -= original['costs'][line['item']]
                    returned_amount[key] -= Decimal(line['amount'])
            reversed_ids.add(ref)
        elif kind == 'OPN':
            for row in d['balances']:
                entry(v,row['account'],**{row['side']:Decimal(row['amount'])})
            for row in d['lines']:
                value=Decimal(row['amount'])
                entry(v,system['inventory'],debit=value)
                move(v,row['item'],Decimal(row['quantity']),value)
            offset=Decimal(d['equity_offset'])
            entry(v,system['opening_equity'],debit=max(offset,ZERO),credit=max(-offset,ZERO))
        else:
            amount, party = Decimal(d['amount']), d['account']
            if kind == 'PAY':
                entry(v, party, debit=amount)
                entry(v, d['cash_account'], credit=amount)
            elif kind == 'REC':
                entry(v, d['cash_account'], debit=amount)
                entry(v, party, credit=amount)
            elif kind == 'PUR':
                entry(v, system['inventory'], debit=amount)
                entry(v, party, credit=amount)
            elif kind == 'SAL':
                entry(v, party, debit=amount)
                entry(v, system['sales'], credit=amount)
            elif kind == 'CN':
                entry(v, system['returns'], debit=amount)
                entry(v, party, credit=amount)
            elif kind == 'DN':
                entry(v, party, debit=amount)
                entry(v, system['inventory'], credit=amount)
            for line in d['lines']:
                item, qty, line_amount = line['item'], Decimal(line['quantity']), Decimal(line['amount'])
                if kind == 'PUR':
                    cost = line_amount
                    move(v, item, qty, cost)
                elif kind == 'SAL':
                    sq, sv = stock[item]
                    if qty > sq:
                        raise PostingError(f"{v['number']}: insufficient stock for the sale.", 'lines')
                    cost = sv if qty == sq else money(sv * qty / sq)
                    move(v, item, -qty, -cost)
                    entry(v, system['cogs'], debit=cost)
                    entry(v, system['inventory'], credit=cost)
                else:
                    ref = d['reference']
                    source = sources.get(ref)
                    required = 'SAL' if kind == 'CN' else 'PUR'
                    if not source or ref in reversed_ids or source['voucher']['kind'] != required:
                        raise PostingError('The return must follow a matching unreversed source voucher.', 'reference')
                    original = source['voucher']['data']
                    ol = next((l for l in original['lines'] if l['item'] == item), None)
                    if not ol or original['account'] != party or Decimal(ol['rate']) != Decimal(line['rate']):
                        raise PostingError('Return account, item and rate must match the original voucher.', 'lines')
                    oq = Decimal(ol['quantity'])
                    previous = returned[(ref,item)]
                    if previous + qty > oq:
                        raise PostingError('Returned quantity exceeds the unreturned original quantity.', 'lines')
                    allocated_amount = max(ZERO,money(Decimal(ol['amount']) * (previous + qty) / oq) - returned_amount[(ref,item)])
                    if allocated_amount != line_amount:
                        raise PostingError('This fractional return produces a paise rounding mismatch with its source. Combine the return quantities into one note.', 'lines')
                    original_cost = source['costs'][item]
                    # Track cost actually still returned, not just quantity: an
                    # earlier partial note may have been reversed out of order.
                    cost = max(ZERO,money(original_cost * (previous + qty) / oq) - returned_cost[(ref,item)])
                    returned[(ref,item)] += qty
                    returned_cost[(ref,item)] += cost
                    returned_amount[(ref,item)] += line_amount
                    if kind == 'CN':
                        move(v, item, qty, cost)
                        entry(v, system['inventory'], debit=cost)
                        entry(v, system['cogs'], credit=cost)
                    else:
                        # Purchase return price must equal allocated original cost.
                        # Any line-rounding residual posts to a visible rounding ledger.
                        move(v, item, -qty, -cost)
                        difference = line_amount - cost
                        if difference > 0:
                            entry(v, system['inventory'], debit=difference)
                            entry(v, system['rounding'], credit=difference)
                        elif difference < 0:
                            entry(v, system['rounding'], debit=-difference)
                            entry(v, system['inventory'], credit=-difference)
                costs[item] = cost
        rows = journal[start_j:]
        if sum((r['debit'] - r['credit'] for r in rows), ZERO) != 0:
            raise PostingError('Unbalanced voucher; nothing was posted.')
        sources[v['id']] = dict(voucher=v, journal=rows, movements=movements[start_m:], costs=costs)
    return journal, movements
