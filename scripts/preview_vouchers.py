#!/usr/bin/env python3
"""Generate synthetic PDF layout evidence without reading or changing a database."""
import os
import sys
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace as Row
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
import pymupdf
from pypdf import PdfWriter,PdfReader
from books.pdf_export import voucher_pdf_bytes
from books.models import Voucher

output=ROOT/'output/pdf';output.mkdir(parents=True,exist_ok=True)
review=ROOT/'tmp/pdfs';review.mkdir(parents=True,exist_ok=True)
workspace=Row(name='Mogra Trading · Sample',address='12 Sample Market Road\nSecond floor',city='Surat',postcode='395001',mobile='+91 90000 00000',email='office@example.test',timezone='Asia/Kolkata')
user=Row(username='demo@example.test')
accounts=[Row(id=uuid.uuid4(),name=name) for name in ['Sample customer','Sample supplier','Cash','General expenses']]
items=[Row(id=uuid.uuid4(),name=f'Sample cotton bag {i:03d}') for i in range(100)]
vouchers={}
for kind,label in Voucher.TYPES:
    amount='125.50' if kind in ['PAY','REC','REV'] else '1000.00'
    data={'amount':amount,'narration':'Synthetic sample for a client demonstration.'}
    if kind in ['PAY','REC']:
        data.update(account=str(accounts[3 if kind=='PAY' else 0].id),cash_account=str(accounts[2].id))
    elif kind in ['PUR','SAL','CN','DN']:
        data.update(account=str(accounts[1 if kind in ['PUR','DN'] else 0].id),lines=[{'item':str(items[0].id),'quantity':'10.000','rate':'100.00','amount':'1000.00'}])
    elif kind=='OPN':
        data.update(amount='2000.00',balances=[{'account':str(accounts[2].id),'side':'debit','amount':'1000.00'}],lines=[{'item':str(items[0].id),'quantity':'10.000','amount':'1000.00'}])
    vouchers[kind]=Row(id=uuid.uuid4(),number=f'{kind}-000001',kind=kind,date=date(2026,10,8),data=data,reverses_id=None,get_kind_display=lambda label=label:label)
for kind,source in [('CN','SAL'),('DN','PUR')]:vouchers[kind].data['reference']=str(vouchers[source].id)
vouchers['REV'].reverses_id=vouchers['REC'].id
def query(**kwargs):
    source=next((row for row in vouchers.values() if str(row.id)==str(kwargs.get('pk'))),None)
    return Row(first=lambda:source,exists=lambda:kwargs.get('reverses') is vouchers['REC'])

combined=PdfWriter()
with patch('books.pdf_export.Account.objects.filter',return_value=accounts),patch('books.pdf_export.Item.objects.filter',return_value=items),patch('books.pdf_export.Voucher.objects.filter',side_effect=query):
    for kind,voucher in vouchers.items():
        content=voucher_pdf_bytes(workspace,voucher,user)
        combined.append(PdfReader(BytesIO(content)))
        document=pymupdf.open(stream=content,filetype='pdf')
        document[0].get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(review/f'{kind}.png')
    long=vouchers['PUR'];long.data['lines']=[{'item':str(item.id),'quantity':'1.000','rate':'100.00','amount':'100.00'} for item in items];long.data['amount']='10000.00'
    for item in items:item.name+=' · Long descriptive item name for wrapping and pagination review'
    content=voucher_pdf_bytes(workspace,long,user)
    (review/'multipage.pdf').write_bytes(content)
    document=pymupdf.open(stream=content,filetype='pdf')
    for index in range(len(document)):document[index].get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(review/f'multipage-{index+1}.png')
    print(f'Multipage layout: {len(document)} pages')
with (output/'simplebooks-voucher-demo.pdf').open('wb') as handle:combined.write(handle)
print(output/'simplebooks-voucher-demo.pdf')
