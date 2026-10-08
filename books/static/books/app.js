'use strict';
const $ = (s, root=document) => root.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = v => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2,minimumFractionDigits:2}).format(Number(v || 0));
const labels = {PAY:'Payment',REC:'Receipt',SAL:'Sales',PUR:'Purchase',CN:'Credit note',DN:'Debit note',REV:'Reversal',OPN:'Opening balances'};
const titles = {dashboard:'Overview',vouchers:'Vouchers',ledger:'Ledger',inventory:'Inventory book',masters:'Accounts & items',opening:'Opening balances',audit:'Activity history'};
const state = {books:{ledger:{q:'',direction:'',sort:'oldest'},inventory:{q:'',direction:'',sort:'oldest'}},masters:{accounts:{q:'',sort:'name',page:1},items:{q:'',sort:'name',page:1}},page:'dashboard',pageNumber:1,kind:'',q:'',sort:'newest',account:'',item:'',data:null};
let draft, openingDraft, detail, loadingToken=0, masterCollection;
const csrf = () => document.cookie.split('; ').find(r=>r.startsWith('csrftoken='))?.split('=')[1] || '';
async function api(path, options={}) {
  const response = await fetch(path,{...options,headers:{'Content-Type':'application/json','X-CSRFToken':csrf(),...options.headers}});
  let body;
  try { body=await response.json(); } catch { throw new Error(`The request could not be completed (${response.status}). Refresh and try again; your draft is saved.`); }
  if(!response.ok) { const e=new Error(body.error || 'Request failed.'); e.field=body.field; e.status=response.status; e.reference=body.reference_id; throw e; }
  return body;
}
function message(text, error=false) { $('#global-message').innerHTML=`<div class="${error?'error':'success'}-message">${esc(text)}</div>`; }
function dateLabel(value) { return new Date(value+'T12:00:00').toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'}); }
function params(extra={}) { return new URLSearchParams({start:state.start,end:state.end,page:state.pageNumber,...extra}); }
function pageHead(title, subtitle, action=true) { return `<div class="page-head"><div><p class="eyebrow">YOUR BUSINESS, AT A GLANCE</p><h1>${title}</h1><p class="muted">${subtitle}</p></div>${action?'<button class="button primary" data-new="PAY">＋ New voucher</button>':''}</div>`; }
function range() { return `<form id="range-form" class="range-bar"><div class="range-fields"><label for="start">From</label><input type="date" id="start" name="start" value="${state.start}" required><label for="end">To</label><input type="date" id="end" name="end" value="${state.end}" required><button class="button small">Apply</button></div><button class="refresh" type="button" data-refresh>↻ Refresh books</button></form>`; }
function empty(title, text, action='') { return `<div class="empty"><strong>${title}</strong>${text}${action}</div>`; }
function pager(d) { return `<div class="pagination"><span>${d.count} records · Page ${d.page} of ${d.pages}</span><div><button class="button small" data-pager="${d.page-1}" ${d.page<=1?'disabled':''}>← Previous</button><button class="button small" data-pager="${d.page+1}" ${d.page>=d.pages?'disabled':''}>Next →</button></div></div>`; }
function voucherRows(rows, mini=false) { return `<div class="table-wrap"><table><thead><tr><th>Voucher</th><th>Type</th><th class="${mini?'hide-mobile':''}">Date</th><th class="num">Amount</th></tr></thead><tbody>${rows.map(v=>`<tr><td><button class="text-link mono" data-voucher="${v.id}">${esc(v.number)}</button></td><td><span class="type-pill ${v.kind}">${labels[v.kind]}</span></td><td class="${mini?'hide-mobile':''}">${dateLabel(v.date)}</td><td class="num">${money(v.data.amount)}</td></tr>`).join('')}</tbody></table></div>`; }
const accountName = id => state.data.accounts.find(a=>a.id===id)?.name || 'Account';
const itemName = id => state.data.items.find(i=>i.id===id)?.name || 'Item';
function options(rows, selected, placeholder='Select…') { return `<option value="">${placeholder}</option>`+rows.map(r=>`<option value="${r.id}" ${r.id===selected?'selected':''}>${esc(r.name)}</option>`).join(''); }
async function refreshBootstrap() { state.data=await api('/api/bootstrap/'); if(state.data.default_cash&&!state.data.accounts.some(a=>a.id===state.data.default_cash.id))state.data.accounts.push(state.data.default_cash); }
const bookArgs=()=>state.books[state.page];
function bookFilters() {
  const b=bookArgs(), ledger=state.page==='ledger';
  return `<form class="filters" id="book-filters"><input name="q" aria-label="Search book movements" placeholder="Voucher number or narration" maxlength="120" value="${esc(b.q)}"><select name="direction" aria-label="Movement direction"><option value="">All movements</option>${(ledger?[['debit','Debits'],['credit','Credits']]:[['inward','Inward stock'],['outward','Outward stock']]).map(([v,l])=>`<option value="${v}" ${b.direction===v?'selected':''}>${l}</option>`).join('')}</select><select name="sort" aria-label="Movement sort order"><option value="oldest">Oldest first</option><option value="newest" ${b.sort==='newest'?'selected':''}>Newest first</option></select><button class="button">Search movements</button></form><p class="filter-caption">Balances cover every movement in the selected period. Search and direction filter the list and export.</p>`;
}
function masterPanel(collection,d) {
  const accounts=collection==='accounts', f=state.masters[collection];
  return `<section class="panel"><div class="panel-head"><h3>${accounts?'Accounts':'Items'} <span class="muted">· ${d.count}</span></h3><button class="button small" data-master="${collection}">＋ ${accounts?'Account':'Item'}</button></div><form class="filters master-filters" data-master-filters="${collection}"><input name="q" aria-label="Search ${collection}" placeholder="Search ${collection}" maxlength="120" value="${esc(f.q)}"><select name="sort" aria-label="Sort ${collection}"><option value="name">A to Z</option><option value="name-desc" ${f.sort==='name-desc'?'selected':''}>Z to A</option></select><button class="button small">Search</button></form>${d.rows.length?`<div class="table-wrap"><table><thead><tr><th>Name</th><th>${accounts?'Group':'Unit'}</th></tr></thead><tbody>${d.rows.map(r=>`<tr><td><button class="text-link" ${accounts?'data-account':'data-item'}="${r.id}">${esc(r.name)}</button>${r.code?'<div class="help">System account</div>':''}</td><td>${esc(accounts?r.kind:r.unit)}</td></tr>`).join('')}</tbody></table></div>`:empty('No matches in this view.','Try another search or add a new record.')}${pager(d).replaceAll('data-pager=',`data-master-page="${collection}" data-master-page-number=`)}</section>`;
}
async function ensureMasters(...sources) {
  const ids={accounts:new Set(),items:new Set()};
  for(const data of [...sources,draft,openingDraft]) {
    if(!data)continue;
    for(const key of ['account','cash_account'])if(data[key]&&data[key]!=='cash-bank')ids.accounts.add(data[key]);
    for(const row of data.balances||[])if(row.account)ids.accounts.add(row.account);
    for(const row of data.lines||[])if(row.item)ids.items.add(row.item);
    if(data.item)ids.items.add(data.item);
  }
  for(const collection of ['accounts','items']) {
    const current=new Map(state.data[collection].map(r=>[r.id,r]));
    const missing=[...ids[collection]].filter(id=>!current.has(id));
    for(let i=0;i<missing.length;i+=200) {
      const result=await api(`/api/masters/${collection}/?`+new URLSearchParams({ids:missing.slice(i,i+200).join(',')}));
      for(const row of result.rows)current.set(row.id,row);
    }
    // Keep the initial choices and the masters needed by current forms/books.
    const keep=new Set([...state.data[collection].slice(0,26).map(r=>r.id),...ids[collection]]);
    state.data[collection]=[...current.values()].filter(row=>keep.has(row.id));
  }
}
const pickerState=new WeakMap();
function enhancePickers(root) {
  for(const select of root.querySelectorAll('#book-account,#book-item,#f-account,#f-cash,select[data-line-field="item"],select[data-opening-field="account"],select[data-opening-field="item"]')) {
    if(pickerState.has(select))continue;
    const collection=select.id==='book-item'||select.dataset.lineField==='item'||select.dataset.openingField==='item'?'items':'accounts';
    let kinds='',nonSystem='';
    if(select.id==='f-cash')kinds='cash,bank';
    if(select.id==='f-account'){nonSystem='1';kinds=['SAL','CN'].includes(draft.kind)?'customer,cash,bank':['PUR','DN'].includes(draft.kind)?'supplier,cash,bank':'';}
    if(select.dataset.openingField==='account')nonSystem='1';
    const label=select.getAttribute('aria-label')||root.querySelector(`label[for="${CSS.escape(select.id)}"]`)?.textContent||collection;
    const wrapper=document.createElement('div');wrapper.className='master-lookup';
    wrapper.innerHTML=`<input type="search" class="master-search" aria-label="Find ${esc(label)}" placeholder="Find ${collection} by name" maxlength="120"><div class="lookup-status" aria-live="polite"><span>Search for more choices.</span><button type="button" class="text-link" data-lookup-page="-1" hidden>Previous</button><button type="button" class="text-link" data-lookup-page="1" hidden>Next</button></div>`;
    select.before(wrapper); wrapper.append(select);
    const input=$('input',wrapper),meta={select,input,wrapper,collection,kinds,nonSystem,q:'',page:1,rows:[],serial:0,timer:null};
    pickerState.set(select,meta);
    input.addEventListener('input',()=>{clearTimeout(meta.timer);meta.q=input.value;meta.page=1;meta.serial++;meta.timer=setTimeout(()=>loadPicker(meta),250);});
    input.addEventListener('focus',()=>{if(!meta.rows.length)loadPicker(meta);});
    select.addEventListener('change',()=>{const row=meta.rows.find(r=>r.id===select.value);if(row&&!state.data[collection].some(r=>r.id===row.id))state.data[collection].push(row);});
  }
}
async function loadPicker(meta) {
  const serial=++meta.serial;
  try {
    const result=await api(`/api/masters/${meta.collection}/?`+new URLSearchParams({q:meta.q,page:meta.page,kinds:meta.kinds,non_system:meta.nonSystem}));
    if(serial!==meta.serial||!meta.select.isConnected)return;
    const selected=meta.select.value;
    const saved=[...meta.select.options].find(o=>o.value===selected);
    meta.rows=result.rows;
    meta.select.innerHTML=options(result.rows,selected);
    if(selected&&!result.rows.some(r=>r.id===selected)&&saved)meta.select.add(new Option(saved.textContent,selected,true,true));
    if(meta.select.id==='book-account'&&![...meta.select.options].some(o=>o.value==='cash-bank'))meta.select.add(new Option('Cash & bank (combined)','cash-bank',selected==='cash-bank',selected==='cash-bank'));
    const status=$('.lookup-status',meta.wrapper);$('span',status).textContent=`${result.count} matches · Page ${result.page} of ${result.pages}`;
    $('[data-lookup-page="-1"]',status).hidden=result.page<=1; $('[data-lookup-page="1"]',status).hidden=result.page>=result.pages;meta.page=result.page;
  } catch(e){if(serial===meta.serial)$('.lookup-status span',meta.wrapper).textContent=e.message;}
}

async function render() {
  const token=++loadingToken;
  document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===state.page));
  $('#breadcrumb').textContent=titles[state.page];
  try {
    let html='';
    if(state.page==='dashboard') {
      const d=await api('/api/dashboard/?'+params());
      html=pageHead('A clear view of your business.','Every entry in its place. Every balance up to date.')+range();
      html+=`<div class="stats"><button class="stat featured" data-cash><span class="stat-label"><span>Cash & bank</span><span>↗</span></span><strong class="stat-value">${money(d.cash)}</strong><span class="stat-note">Balance as of ${dateLabel(state.end)}</span></button>${[['SAL','Sales','Revenue for the selected period'],['PUR','Purchases','Stock purchased this period'],['REC','Receipts','Money received this period']].map(([k,l,n])=>`<button class="stat" data-kind="${k}"><span class="stat-label"><span>${l}</span><span>↗</span></span><strong class="stat-value">${money(d.totals[k])}</strong><span class="stat-note">${n}</span></button>`).join('')}</div>`;
      html+=`<div class="section-grid"><div><section class="panel"><div class="panel-head"><div><h3>Recent vouchers</h3><p>${d.voucher_count} entries in the selected period</p></div><button class="text-link" data-page="vouchers">View all ↗</button></div>${d.recent.length?voucherRows(d.recent,true):empty('Your books start here.','Add an account or item, then post your first voucher.','<br><button class="button small" data-page="masters">Set up accounts & items →</button>')}</section><div class="sub-stats"><div class="mini-stat"><small>To receive · at period end</small><strong>${money(d.receivable)}</strong></div><div class="mini-stat"><small>To pay · at period end</small><strong>${money(d.payable)}</strong></div><div class="mini-stat"><small>Stock value · at period end</small><strong>${money(d.stock_value)}</strong></div></div><p class="help">Last refreshed ${new Date(d.refreshed_at).toLocaleTimeString('en-IN')} · Summary amounts include reversals.</p></div><aside><section class="panel"><div class="panel-head"><h3>Make an entry</h3></div><div class="quick-list">${[['REC','↙','Money coming in'],['PAY','↗','Money going out'],['SAL','↑','Goods sold'],['PUR','↓','Goods purchased'],['CN','↶','A customer return'],['DN','↷','A supplier return']].map(([k,icon,sub])=>`<button class="quick-row" data-new="${k}"><span class="quick-icon">${icon}</span><div><strong>${labels[k]}</strong><small>${sub}</small></div><span>›</span></button>`).join('')}</div></section><div class="note"><strong>A little more peace of mind.</strong><p>Each posted entry keeps its history. Corrections update your books together, so your ledger and inventory stay in step.</p></div></aside></div>`;
      html+=`<div class="sub-stats">${[['PAY','Payments'],['CN','Credit notes'],['DN','Debit notes']].map(([k,l])=>`<button class="stat" data-kind="${k}"><span class="stat-label">${l}<span>↗</span></span><strong class="stat-value">${money(d.totals[k])}</strong><span class="stat-note">Selected period, net of reversals</span></button>`).join('')}</div>`;
    } else if(state.page==='vouchers') {
      const d=await api('/api/vouchers/?'+params({kind:state.kind,q:state.q,sort:state.sort}));
      html=pageHead('Every entry, accounted for.','Browse, review and correct your posted vouchers.')+range()+`<form class="filters" id="voucher-filters"><select name="kind" aria-label="Voucher type"><option value="">All voucher types</option>${Object.entries(labels).map(([k,v])=>`<option value="${k}" ${state.kind===k?'selected':''}>${v}</option>`).join('')}</select><input name="q" placeholder="Voucher number or narration" aria-label="Search vouchers" value="${esc(state.q)}"><select name="sort" aria-label="Sort order"><option value="newest">Newest first</option><option value="oldest" ${state.sort==='oldest'?'selected':''}>Oldest first</option></select><button class="button">Search</button><a class="button" href="/api/export/vouchers.csv?${params({kind:state.kind,q:state.q,sort:state.sort})}">↓ Export CSV</a></form><section class="panel">${d.rows.length?voucherRows(d.rows):empty('No vouchers in this view.','Try another period or create your first entry.')}${pager(d)}</section>`;
    } else if(state.page==='ledger') {
      await ensureMasters({account:state.account});
      html=pageHead('Follow the money.','A clear record of every debit and credit.')+range()+`<div class="filters"><select id="book-account" aria-label="Ledger account">${options(state.data.accounts,state.account,'Choose an account')}<option value="cash-bank" ${state.account==='cash-bank'?'selected':''}>Cash & bank (combined)</option></select>${state.account?`<a class="button" href="/api/export/ledger.csv?${params({account:state.account,...bookArgs()})}">↓ Export CSV</a>`:''}</div>`;
      if(state.account) {
        html+=bookFilters();
        const d=await api('/api/ledger/?'+params({account:state.account,...bookArgs()}));
        html+=`<p class="filter-caption">Positive balance = debit · Negative balance = credit</p><div class="book-summary"><div><small>Opening balance</small><strong>${money(d.opening)}</strong></div><div><small>Debits / Credits</small><strong>${money(d.debit)}</strong><div class="help">${money(d.credit)} credited</div></div><div><small>Closing balance</small><strong>${money(d.closing)}</strong></div></div><section class="panel">${d.rows.length?`<div class="table-wrap"><table><thead><tr><th>Date</th><th>Source voucher</th><th>Account</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>${d.rows.map(r=>`<tr><td>${dateLabel(r.date)}</td><td><button class="text-link mono" data-voucher="${r.voucher}">${r.number}</button></td><td>${esc(r.account)}</td><td class="num">${money(r.debit)}</td><td class="num">${money(r.credit)}</td></tr>`).join('')}</tbody></table></div>`:empty('No movements in this period.','Your opening balance is shown above.')}${pager(d)}</section>`;
      } else html+=`<section class="panel">${empty('Pick an account to open its book.','View balances, trace vouchers and export your ledger.')}</section>`;
    } else if(state.page==='inventory') {
      await ensureMasters({item:state.item});
      html=pageHead('Know what’s on your shelf.','Item movements and value, connected to their source.')+range()+`<div class="filters"><select id="book-item" aria-label="Inventory item">${options(state.data.items,state.item,'Choose an item')}</select><button class="button" data-master="items">＋ New item</button>${state.item?`<a class="button" href="/api/export/inventory.csv?${params({item:state.item,...bookArgs()})}">↓ Export CSV</a>`:''}</div>`;
      if(state.item) {
        html+=bookFilters();
        const d=await api('/api/inventory/?'+params({item:state.item,...bookArgs()}));
        html+=`<div class="book-summary"><div><small>Opening quantity · ${esc(d.unit)}</small><strong>${d.opening.quantity}</strong><div class="help">${money(d.opening.value)}</div></div><div><small>Closing quantity · ${esc(d.unit)}</small><strong>${d.closing.quantity}</strong></div><div><small>Closing stock value</small><strong>${money(d.closing.value)}</strong></div></div><p class="filter-caption">Positive movements = inward · Negative movements = outward · Moving weighted average</p><section class="panel">${d.rows.length?`<div class="table-wrap"><table><thead><tr><th>Date / source</th><th class="num">Qty movement</th><th class="num">Value</th><th class="num">Qty balance</th><th class="num">Stock value</th></tr></thead><tbody>${d.rows.map(r=>`<tr><td>${dateLabel(r.date)}<br><button class="text-link mono" data-voucher="${r.voucher}">${r.number}</button></td><td class="num">${r.quantity}</td><td class="num">${money(r.value)}</td><td class="num">${r.balance_quantity}</td><td class="num">${money(r.balance_value)}</td></tr>`).join('')}</tbody></table></div>`:empty('No stock movements in this period.','Post a purchase to bring stock into your books.')}${pager(d)}</section>`;
      } else html+=`<section class="panel">${empty('Choose an item to see its journey.','Purchases, sales and returns all appear in one place.')}</section>`;
    } else if(state.page==='masters') {
      const lists=await Promise.all(['accounts','items'].map(collection=>api(`/api/masters/${collection}/?`+new URLSearchParams(state.masters[collection]))));
      html=pageHead('The building blocks of your books.','Set up the people, accounts and items your business uses.',false)+`<div class="master-grid">${masterPanel('accounts',lists[0])}${masterPanel('items',lists[1])}</div><div class="note"><strong>Bringing existing books across?</strong><p>Enter your starting account balances and item quantities in Opening balances. Existing stock is valued at cost and is not treated as a new purchase.</p><button class="text-link" data-page="opening">Set up opening balances →</button></div>`;
    } else if(state.page==='opening') {
      const result=await api('/api/opening/');
      if(!openingDraft) {
        try { openingDraft=JSON.parse(localStorage.getItem(openingKey())); } catch {}
        if(!openingDraft) openingDraft=result.voucher?{...result.voucher.data,id:result.voucher.id,version:result.voucher.version,reason:'',key:crypto.randomUUID()}:{kind:'OPN',date:state.data.today,balances:[],lines:[],key:crypto.randomUUID()};
      }
      await ensureMasters(openingDraft);
      html=pageHead('Start with the right balances.','Bring your existing cash, parties and stock into these books.',false)+openingForm();
    } else {
      const d=await api('/api/audit/?'+params());
      html=pageHead('A history you can follow.','Workspace activity, posting and corrections, preserved in order.',false)+`<section class="panel"><div class="table-wrap"><table><thead><tr><th>When</th><th>Action</th><th>Details</th><th class="hide-mobile">By</th></tr></thead><tbody>${d.rows.map(r=>`<tr><td>${esc(new Date(r.at).toLocaleString('en-IN'))}</td><td>${esc(r.action)}</td><td>${esc(r.details.number || r.details.name || r.details.reason || '—')}${r.details.reason?`<div class="help">${esc(r.details.reason)}</div>`:''}</td><td class="hide-mobile">${esc(r.actor)}</td></tr>`).join('')}</tbody></table></div>${pager(d)}</section>`;
    }
    if(token===loadingToken) { $('#content').innerHTML=html; labelTables($('#content')); enhancePickers($('#content')); }
  } catch(e) { message(e.message + (e.reference?` Reference: ${e.reference}`:''),true); }
}
function labelTables(root) { root.querySelectorAll('table').forEach(table=>{ const headings=Array.from(table.querySelectorAll('thead th')).map(th=>th.textContent); table.classList.add('responsive-table'); table.querySelectorAll('tbody tr').forEach(row=>Array.from(row.children).forEach((cell,i)=>{cell.dataset.label=headings[i]||'';})); }); }
function navigate(page) { $('#global-message').innerHTML=''; state.page=page; state.pageNumber=1; render(); }
const draftKey=()=>`simplebooks:draft:${state.data.workspace.id}`;
function saveDraft() { try { localStorage.setItem(draftKey(),JSON.stringify(draft)); $('#draft-status').textContent=draft.pending?'Submission uncertain · retry this exact voucher':'Draft saved on this device'; } catch { $('#draft-status').textContent='Browser storage unavailable. Keep this window open.'; } }
function parseScaled(value,places) {
  if(!/^\d+(\.\d+)?$/.test(value || '')) return null;
  let [a,b='']=value.split('.');
  if(b.length>places || a.length>9) return null;
  return BigInt(a)*10n**BigInt(places)+BigInt(b.padEnd(places,'0'));
}
function paiseText(n) { const sign=n<0n?'-':'';n=n<0n?-n:n;return `${sign}${n/100n}.${String(n%100n).padStart(2,'0')}`; }
const openingKey=()=>`simplebooks:opening:${state.data.workspace.id}`;
function openingTotals() {
  let debit=0n,credit=0n;
  for(const row of openingDraft.balances) {const amount=parseScaled(row.amount,2)||0n;if(row.side==='debit')debit+=amount;else credit+=amount;}
  for(const row of openingDraft.lines) debit+=parseScaled(row.amount,2)||0n;
  return {debit,credit,offset:credit-debit,total:debit>credit?debit:credit};
}
function openingSummary() {
  const t=openingTotals();
  return `<div class="book-summary"><div><small>Entered debits + stock</small><strong>${money(paiseText(t.debit))}</strong></div><div><small>Entered credits</small><strong>${money(paiseText(t.credit))}</strong></div><div><small>Offset to opening equity · ${t.offset>0n?'debit':'credit'}</small><strong>${money(paiseText(t.offset<0n?-t.offset:t.offset))}</strong></div></div>`;
}
function saveOpeningDraft() {try{localStorage.setItem(openingKey(),JSON.stringify(openingDraft));}catch{message('Browser storage is unavailable. Keep the opening-balance form open until it is saved.',true);}}
function openingForm() {
  const d=openingDraft;
  return `<form id="opening-form"><div class="note opening-note"><strong>${d.id?'Correct starting balances with full history.':'One starting point for your business.'}</strong><p>Choose a date on or before your first voucher. These are the balances at the beginning of that date. Stock value posts to Inventory; the net difference posts to Opening balance equity. Starting stock is not a purchase or an expense.</p></div><fieldset class="editor-fieldset" ${d.pending?'disabled':''}><div class="field opening-date"><label for="opening-date">Opening date</label><input id="opening-date" name="date" type="date" value="${esc(d.date)}" required></div><section class="panel opening-panel"><div class="panel-head"><div><h3>Account balances</h3><p>Cash, bank, customers, suppliers and other existing balances.</p></div><button class="button small" data-opening-add="balances" type="button">＋ Account</button></div><div class="opening-rows">${d.balances.length?d.balances.map((r,i)=>`<div class="opening-row" data-opening-group="balances" data-opening-row="${i}"><div><label for="oa-${i}">Account</label><select id="oa-${i}" data-opening-field="account" required>${options(state.data.accounts.filter(a=>!a.code),r.account)}</select></div><div><label for="os-${i}">Side</label><select id="os-${i}" data-opening-field="side"><option value="debit" ${r.side==='debit'?'selected':''}>Debit</option><option value="credit" ${r.side==='credit'?'selected':''}>Credit</option></select></div><div><label for="ov-${i}">Amount · INR</label><input id="ov-${i}" data-opening-field="amount" value="${esc(r.amount)}" inputmode="decimal" required></div><button class="icon-button" type="button" data-opening-remove="${i}" data-opening-list="balances" aria-label="Remove account row ${i+1}">×</button></div>`).join(''):'<p class="muted">No account balances added. Add only accounts that have a starting balance.</p>'}<p class="help">Typically: cash, bank and amounts customers owe you are debits; amounts you owe suppliers and owner capital are credits.</p></div></section><section class="panel opening-panel"><div class="panel-head"><div><h3>Opening stock</h3><p>Physical quantities and their total cost value.</p></div><button class="button small" data-opening-add="lines" type="button">＋ Item</button></div><div class="opening-rows">${d.lines.length?d.lines.map((r,i)=>`<div class="opening-row" data-opening-group="lines" data-opening-row="${i}"><div><label for="oi-${i}">Item</label><select id="oi-${i}" data-opening-field="item" required>${options(state.data.items,r.item)}</select></div><div><label for="oq-${i}">Quantity</label><input id="oq-${i}" data-opening-field="quantity" value="${esc(r.quantity)}" inputmode="decimal" required></div><div><label for="oc-${i}">Total cost · INR</label><input id="oc-${i}" data-opening-field="amount" value="${esc(r.amount)}" inputmode="decimal" required></div><button class="icon-button" type="button" data-opening-remove="${i}" data-opening-list="lines" aria-label="Remove stock row ${i+1}">×</button></div>`).join(''):'<p class="muted">No opening stock added. Item value is cost, not its selling price.</p>'}</div></section><div id="opening-summary">${openingSummary()}</div>${d.id?`<div class="field"><label for="opening-reason">Reason for correction</label><input id="opening-reason" name="reason" value="${esc(d.reason)}" maxlength="500" required><p class="help">Later stock costs and balances will be recalculated. A correction that causes negative stock is rejected.</p></div>`:''}</fieldset><div id="opening-error" class="error-box" role="alert" hidden></div><div class="dialog-footer"><span class="muted">${d.pending?'Submission uncertain. Retry to resolve the same request.':d.id?`Posted opening · version ${d.version}`:'Unsaved starting balances'}</span><button class="button primary" type="submit">${d.pending?'Retry same submission →':d.id?'Save opening correction →':'Post opening balances →'}</button></div><button class="text-link" id="reload-opening" type="button" ${d.pending?'disabled':''}>Discard local changes & reload posted values</button></form>`;
}
function refreshOpeningForm() {$('#opening-form').outerHTML=openingForm();enhancePickers($('#opening-form'));saveOpeningDraft();}
async function submitOpening(event) {
  event.preventDefault();
  const d=openingDraft;
  const payload=d.pending?.payload||{kind:'OPN',date:d.date,balances:d.balances,lines:d.lines,expected_total:paiseText(openingTotals().total),...(d.id?{version:d.version,reason:d.reason}:{})};
  d.pending={payload};saveOpeningDraft();refreshOpeningForm();const button=$('button[type=submit]',$('#opening-form'));button.disabled=true;
  try {
    await api(d.id?`/api/vouchers/${d.id}/`:'/api/vouchers/',{method:d.id?'PUT':'POST',headers:{'Idempotency-Key':d.key},body:JSON.stringify(payload)});
    try{localStorage.removeItem(openingKey());}catch{}
    openingDraft=null;message('Opening balances saved. Your ledger and stock costs have been recalculated.');await render();
  } catch(e) {
    if(e.status&&e.status<500&&e.status!==401){delete d.pending;if(e.status!==409)d.key=crypto.randomUUID();}
    refreshOpeningForm();const box=$('#opening-error');box.hidden=false;box.textContent=e.message+(e.reference?` Reference: ${e.reference}`:'');
  } finally {button.disabled=false;}
}
function totalPaise(d) {
  if(['PAY','REC'].includes(d.kind)) return parseScaled(d.amount,2) || 0n;
  return (d.lines||[]).reduce((sum,l)=>{const q=parseScaled(l.quantity,3),r=parseScaled(l.rate,2);return sum+(q!==null&&r!==null?(q*r+500n)/1000n:0n);},0n);
}
function decimalTotal(d) { const n=totalPaise(d);return `${n/100n}.${String(n%100n).padStart(2,'0')}`; }
function freshDraft(kind) { return {kind,date:state.data.today,account:'',cash_account:state.data.default_cash?.id||'',amount:'',narration:'',lines:[{item:'',quantity:'1',rate:''}],key:crypto.randomUUID()}; }
async function openEditor(kind='PAY', editing=null) {
  if(editing) {
    let saved;
    try{saved=JSON.parse(localStorage.getItem(draftKey()));}catch{}
    if(saved?.pending && saved.id!==editing.id){message('Resolve the pending voucher by opening New voucher and retrying it before editing another.',true);return;}
    if(saved?.id===editing.id) draft=saved;
    else draft={...editing.data,id:editing.id,version:editing.version,key:crypto.randomUUID(),reason:'',reference_number:editing.reference_number||''};
  } else {
    try{draft=JSON.parse(localStorage.getItem(draftKey()));}catch{draft=null;}
    if(!draft) draft=freshDraft(kind);
  }
  try{await ensureMasters(draft);}catch(e){message(e.message,true);return;}
  $('#editor-title').textContent=draft.id?'Correct posted voucher':'New voucher';
  editorFields();$('#voucher-error').hidden=true;$('#editor').showModal();saveDraft();
}
function editorFields() {
  const cash=['PAY','REC'].includes(draft.kind), note=['CN','DN'].includes(draft.kind);
  const partyKinds=['SAL','CN'].includes(draft.kind)?['customer','cash','bank']:['PUR','DN'].includes(draft.kind)?['supplier','cash','bank']:null;
  const accounts=state.data.accounts.filter(a=>!a.code&&(!partyKinds||partyKinds.includes(a.kind)));
  $('#voucher-fields').innerHTML=`<fieldset ${draft.pending?'disabled':''} class="editor-fieldset"><div class="field-grid"><div class="field"><label for="f-kind">Voucher type</label><select id="f-kind" name="kind" ${draft.id?'disabled':''}>${Object.entries(labels).filter(([k])=>!['REV','OPN'].includes(k)).map(([k,v])=>`<option value="${k}" ${draft.kind===k?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label for="f-date">Date</label><input id="f-date" name="date" type="date" value="${esc(draft.date)}" required></div>${note?`<div class="field wide"><label for="reference-number">Original ${draft.kind==='CN'?'sales':'purchase'} voucher number</label><div class="reference-row"><input id="reference-number" name="reference_number" placeholder="${draft.kind==='CN'?'SAL':'PUR'}-000001" value="${esc(draft.reference_number||'')}"><button class="button" type="button" id="load-reference">Load items</button></div><p class="help">${draft.reference?'Source voucher linked. Adjust quantities to the actual return.':'Load the original voucher to retain its account, items and rates.'}</p></div>`:''}<div class="field ${cash?'':'wide'}"><label for="f-account">${cash?'Party / account':draft.kind==='SAL'||draft.kind==='CN'?'Customer / cash / bank':'Supplier / cash / bank'}</label><select id="f-account" name="account" required>${options(accounts,draft.account)}</select><div class="help">Create missing accounts in Accounts & items.</div></div>${cash?`<div class="field"><label for="f-cash">Cash / bank account</label><select id="f-cash" name="cash_account" required>${options(state.data.accounts.filter(a=>['cash','bank'].includes(a.kind)),draft.cash_account)}</select></div><div class="field wide"><label for="f-amount">Amount · INR</label><input id="f-amount" name="amount" inputmode="decimal" value="${esc(draft.amount)}" placeholder="0.00" required></div>`:''}</div>${!cash?`<div><label>Item details</label>${draft.lines.map((l,i)=>`<div class="line-item" data-line="${i}"><div><label for="item-${i}">Item</label><select id="item-${i}" data-line-field="item" required>${options(state.data.items,l.item)}</select></div><div><label for="qty-${i}">Quantity</label><input id="qty-${i}" data-line-field="quantity" value="${esc(l.quantity)}" inputmode="decimal" required></div><div><label for="rate-${i}">Rate · ₹</label><input id="rate-${i}" data-line-field="rate" value="${esc(l.rate)}" inputmode="decimal" required></div><button class="icon-button" type="button" data-remove-line="${i}" aria-label="Remove line ${i+1}">×</button></div>`).join('')}<button class="text-link" type="button" id="add-line">＋ Add another item</button></div>`:''}<div class="total-row"><span>Voucher total</span><strong id="voucher-total">${money(decimalTotal(draft))}</strong></div><div class="field"><label for="f-narration">Narration <span class="muted">· optional</span></label><textarea id="f-narration" name="narration" maxlength="500" placeholder="What is this entry for?">${esc(draft.narration)}</textarea></div>${draft.id?`<div class="field"><label for="f-reason">Reason for correction</label><input id="f-reason" name="reason" maxlength="500" value="${esc(draft.reason)}" required><p class="help">The original values stay in history. This replaces the current accounting and stock effects.</p></div>`:''}</fieldset><button class="text-link" id="discard-draft" type="button" ${draft.pending?'disabled':''}>Discard this draft</button>`;
  enhancePickers($('#voucher-fields'));
  $('#post-button').textContent=draft.pending?'Retry same submission →':draft.id?'Save correction →':'Post voucher →';
}
function showVoucherError(e) {
  const box=$('#voucher-error');box.textContent=e.message+(e.reference?` Reference: ${e.reference}`:'');box.hidden=false;
  document.querySelectorAll('.field-error').forEach(el=>el.remove());
  if(e.field&&e.field!=='__all__') {
    const input=$(`[name="${CSS.escape(e.field)}"]`,$('#voucher-form'));
    if(input){const p=document.createElement('p');p.className='field-error';p.textContent=e.message;input.after(p);input.focus();}
  }
}
async function submitVoucher(event) {
  event.preventDefault();
  const button=$('#post-button');button.disabled=true;$('#voucher-error').hidden=true;
  const payload=draft.pending?.payload || Object.fromEntries(Object.entries({...draft,expected_total:decimalTotal(draft)}).filter(([k])=>!['key','pending','id','reference_number'].includes(k)));
  draft.pending={payload};saveDraft();editorFields();button.disabled=true;
  try {
    const result=await api(draft.id?`/api/vouchers/${draft.id}/`:'/api/vouchers/',{method:draft.id?'PUT':'POST',headers:{'Idempotency-Key':draft.key},body:JSON.stringify(payload)});
    try{localStorage.removeItem(draftKey());}catch{}draft=null;$('#editor').close();message(`${result.number||'Voucher'} ${result.duplicate?'was already posted; no duplicate was created.':'saved. Your ledger and inventory are updated.'}`);await render();
  } catch(e) {
    if(e.status && e.status<500 && e.status!==401) {
      delete draft.pending;
      // Validation failures are atomic; a fresh key is safe after correction.
      if(e.status!==409) draft.key=crypto.randomUUID();
    }
    saveDraft();editorFields();showVoucherError(e);
  } finally {button.disabled=false;}
}
async function openDetail(id) {
  try {
    detail=await api(`/api/vouchers/${id}/`);
    await ensureMasters(detail.data);
    const d=detail;
    $('#detail-content').innerHTML=`<div class="dialog-head"><div><p class="eyebrow">${labels[d.kind]} · VERSION ${d.version}${d.reversed?' · REVERSED':''}</p><h2 id="detail-title">${d.number}</h2></div><button class="icon-button" data-close="detail" aria-label="Close voucher">×</button></div><div class="detail-meta"><div><small>Date</small>${dateLabel(d.date)}</div><div><small>Amount</small>${money(d.data.amount)}</div><div><small>Account</small>${esc(d.data.account?accountName(d.data.account):d.kind==='OPN'?'Opening balances':'Compensating entry')}</div><div><small>Narration</small>${esc(d.data.narration||'—')}</div></div>${d.data.reference?`<p class="help">Return against <button class="text-link" data-voucher="${esc(d.data.reference)}">original voucher ↗</button></p>`:''}${d.reverses?`<p class="help">Reverses <button class="text-link" data-voucher="${d.reverses}">original voucher ↗</button></p>`:''}${d.data.lines?.length?`<div class="table-wrap"><table><thead><tr><th>Item</th><th class="num">Quantity</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead><tbody>${d.data.lines.map(l=>`<tr><td>${esc(itemName(l.item))}</td><td class="num">${l.quantity}</td><td class="num">${l.rate?money(l.rate):'—'}</td><td class="num">${money(l.amount)}</td></tr>`).join('')}</tbody></table></div>`:''}<h3>Accounting entries</h3><div class="table-wrap"><table><thead><tr><th>Account</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>${d.journal.map(r=>`<tr><td>${esc(r.account__name)}</td><td class="num">${money(r.debit)}</td><td class="num">${money(r.credit)}</td></tr>`).join('')}</tbody></table></div><h3>Revision history</h3>${d.history.map(h=>`<details class="history"><summary>Version ${h.version} · ${esc(h.reason)}</summary><p>${esc(h.actor__username)} · ${new Date(h.created_at).toLocaleString('en-IN')}</p><pre>${esc(JSON.stringify(h.data,null,2))}</pre></details>`).join('')}${d.kind==='OPN'?'<div class="dialog-footer"><button class="button" id="edit-opening">Correct opening balances</button></div>':''}${!d.reversed&&!['REV','OPN'].includes(d.kind)?`<div class="dialog-footer"><button class="button" id="edit-voucher">Edit with history</button><button class="button danger" id="show-reversal">Reverse voucher</button></div><form id="reversal-form" hidden><div class="note"><strong>This will create a compensating voucher.</strong><p>The original remains in your history. Accounting and stock effects are reversed on the date below. Review linked returns first.</p></div><div class="field"><label for="reverse-date">Reversal date</label><input type="date" id="reverse-date" required value="${state.data.today}" min="${d.date}"></div><div class="field"><label for="reverse-reason">Reason</label><input id="reverse-reason" required maxlength="500"></div><p id="reverse-error" class="error-text" role="alert"></p><button class="button danger" type="submit">Confirm reversal</button></form>`:''}`;
    labelTables($('#detail')); if(!$('#detail').open) $('#detail').showModal();
  } catch(e){message(e.message,true);}
}
function openMaster(collection) {
  masterCollection=collection;const account=collection==='accounts';
  $('#master-title').textContent=account?'New account':'New item';$('#master-error').textContent='';
  $('#master-fields').innerHTML=`<div class="field"><label for="master-name">Name</label><input id="master-name" name="name" maxlength="120" required></div>${account?`<div class="field"><label for="master-kind">Account group</label><select id="master-kind" name="kind">${['customer','supplier','expense','income','cash','bank','asset','liability','equity'].map(k=>`<option value="${k}">${k[0].toUpperCase()+k.slice(1)}</option>`).join('')}</select></div>`:'<div class="field"><label for="master-unit">Unit</label><input id="master-unit" name="unit" value="pcs" maxlength="20" required><p class="help">For example: pcs, kg, box. Quantities support 3 decimal places.</p></div>'}`;$('#master-dialog').showModal();
}
document.addEventListener('click',async event=>{
  const el=event.target.closest('button,a');if(!el)return;
  if(el.dataset.page) navigate(el.dataset.page);
  if(el.dataset.new) openEditor(el.dataset.new);
  if(el.dataset.close) $('#'+el.dataset.close).close();
  if(el.hasAttribute('data-refresh')) render();
  if(el.dataset.kind){state.kind=el.dataset.kind;navigate('vouchers');}
  if(el.hasAttribute('data-cash')){state.account='cash-bank';navigate('ledger');}
  if(el.dataset.masterPage){state.masters[el.dataset.masterPage].page=Number(el.dataset.masterPageNumber);render();}
  if(el.dataset.lookupPage){const meta=pickerState.get($('select',el.closest('.master-lookup')));meta.page+=Number(el.dataset.lookupPage);loadPicker(meta);}
  if(el.dataset.pager){state.pageNumber=Number(el.dataset.pager);render();}
  if(el.dataset.voucher) openDetail(el.dataset.voucher);
  if(el.dataset.account){state.account=el.dataset.account;navigate('ledger');}
  if(el.dataset.item){state.item=el.dataset.item;navigate('inventory');}
  if(el.dataset.master) openMaster(el.dataset.master);
  if(el.dataset.openingAdd){const group=el.dataset.openingAdd;openingDraft[group].push(group==='balances'?{account:'',side:'debit',amount:''}:{item:'',quantity:'',amount:''});refreshOpeningForm();}
  if(el.dataset.openingRemove!==undefined){openingDraft[el.dataset.openingList].splice(Number(el.dataset.openingRemove),1);refreshOpeningForm();}
  if(el.id==='reload-opening'&&confirm('Discard the unsaved opening-balance changes on this device and reload the posted values? Posted records are unaffected.')){try{localStorage.removeItem(openingKey());}catch{}openingDraft=null;render();}
  if(el.id==='edit-opening'){$('#detail').close();navigate('opening');}
  if(el.id==='add-line'){if(draft.lines.length<100){draft.lines.push({item:'',quantity:'1',rate:''});editorFields();saveDraft();}}
  if(el.dataset.removeLine!==undefined){draft.lines.splice(Number(el.dataset.removeLine),1);editorFields();saveDraft();}
  if(el.id==='discard-draft'&&confirm('Discard the unsaved voucher on this device? Posted records are unaffected.')){localStorage.removeItem(draftKey());draft=null;$('#editor').close();}
  if(el.id==='load-reference') {
    try {
      const number=$('#reference-number').value.trim().toUpperCase();
      if(!/^(SAL|PUR)-\d+$/.test(number)) throw new Error('Enter the full original voucher number.');
      const result=await api('/api/vouchers/?'+new URLSearchParams({start:'1900-01-01',end:'9999-12-31',kind:draft.kind==='CN'?'SAL':'PUR',q:number}));
      const v=result.rows[0];if(!v)throw new Error('Original voucher not found in your workspace.');
      draft.reference=v.id;draft.reference_number=v.number;draft.account=v.data.account;draft.lines=structuredClone(v.data.lines);await ensureMasters(draft);editorFields();saveDraft();
    }catch(e){showVoucherError(e);}
  }
  if(el.id==='edit-voucher'){$('#detail').close();if(detail.data.reference){try{const source=await api(`/api/vouchers/${detail.data.reference}/`);detail.reference_number=source.number;}catch{}}openEditor(detail.kind,detail);}
  if(el.id==='show-reversal'){$('#reversal-form').hidden=false;$('#reverse-reason').focus();}
});
document.addEventListener('input',event=>{
  if(event.target.classList.contains('master-search'))return;
  if(event.target.closest('#opening-form')) {
    if(openingDraft?.pending)return;
    const el=event.target;
    if(el.dataset.openingField){const row=el.closest('[data-opening-row]');openingDraft[row.dataset.openingGroup][Number(row.dataset.openingRow)][el.dataset.openingField]=el.value;}
    else if(el.name)openingDraft[el.name]=el.value;
    $('#opening-summary').innerHTML=openingSummary();saveOpeningDraft();return;
  }
  if(!event.target.closest('#voucher-form')||draft?.pending)return;
  const el=event.target;
  if(el.dataset.lineField) draft.lines[Number(el.closest('[data-line]').dataset.line)][el.dataset.lineField]=el.value;
  else if(el.name) {draft[el.name]=el.value;if(el.name==='reference_number')delete draft.reference;}
  if(el.name==='kind'){draft.lines=[{item:'',quantity:'1',rate:''}];draft.account='';delete draft.reference;draft.reference_number='';editorFields();}
  if($('#voucher-total'))$('#voucher-total').textContent=money(decimalTotal(draft));saveDraft();
});
document.addEventListener('change',event=>{
  if(event.target.id==='book-account'){state.account=event.target.value;state.pageNumber=1;render();}
  if(event.target.id==='book-item'){state.item=event.target.value;state.pageNumber=1;render();}
});
document.addEventListener('submit',async event=>{
  const form=event.target;
  if(form.id==='range-form'){event.preventDefault();state.start=form.start.value;state.end=form.end.value;state.pageNumber=1;render();}
  if(form.id==='voucher-filters'){event.preventDefault();const data=new FormData(form);state.kind=data.get('kind');state.q=data.get('q');state.sort=data.get('sort');state.pageNumber=1;render();}
  if(form.id==='book-filters'){event.preventDefault();state.books[state.page]=Object.fromEntries(new FormData(form));state.pageNumber=1;render();}
  if(form.dataset.masterFilters){event.preventDefault();state.masters[form.dataset.masterFilters]={...Object.fromEntries(new FormData(form)),page:1};render();}
  if(form.id==='voucher-form')submitVoucher(event);
  if(form.id==='opening-form')submitOpening(event);
  if(form.id==='master-form'){
    event.preventDefault();const button=$('button[type=submit]',form);button.disabled=true;
    try{await api('/api/masters/'+masterCollection+'/',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});await refreshBootstrap();$('#master-dialog').close();message('Saved to your workspace.');render();}catch(e){$('#master-error').textContent=e.message;}finally{button.disabled=false;}
  }
  if(form.id==='reversal-form'){
    event.preventDefault();const button=$('button[type=submit]',form);button.disabled=true;
    const key='simplebooks:reverse:'+detail.id;
    let saved;try{saved=JSON.parse(localStorage.getItem(key));}catch{}
    const payload=saved?.payload||{version:detail.version,date:$('#reverse-date').value,reason:$('#reverse-reason').value};
    const attempt=saved||{key:crypto.randomUUID(),payload};localStorage.setItem(key,JSON.stringify(attempt));
    try{await api(`/api/vouchers/${detail.id}/reverse/`,{method:'POST',headers:{'Idempotency-Key':attempt.key},body:JSON.stringify(payload)});localStorage.removeItem(key);$('#detail').close();message('Reversal posted. The original remains in history.');render();}catch(e){if(e.status&&e.status<500&&e.status!==401)localStorage.removeItem(key);$('#reverse-error').textContent=e.message+' If the result is uncertain, retry to check the same submission.';}finally{button.disabled=false;}
  }
});
window.addEventListener('offline',()=>message('You are offline. Your voucher draft is kept on this device. Posting requires a connection.',true));
window.addEventListener('online',()=>message('Connection restored. Review your draft and retry any pending submission.'));
(async()=>{try{await refreshBootstrap();state.end=state.data.today;state.start=state.end.slice(0,8)+'01';await render();}catch(e){message(e.message,true);$('#content').innerHTML=empty('Your workspace could not load.','Refresh the page or sign in again.','<br><a class="button" href="/login/">Sign in</a>');}})();
