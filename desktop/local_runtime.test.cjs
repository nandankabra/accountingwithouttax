'use strict';
const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const os=require('node:os');const crypto=require('node:crypto');
const {LocalRuntime,installation}=require('./local_runtime.cjs');
test('installation identity persists and damaged identity is never replaced',()=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'simplebooks-id-'));try{const id=installation(dir);assert.equal(installation(dir),id);fs.writeFileSync(path.join(dir,'installation.json'),'broken');assert.throws(()=>installation(dir));}finally{fs.rmSync(dir,{recursive:true,force:true});}});
test('standalone engine activates, posts, exports, restarts and restores offline', {timeout:120000}, async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'Simple Books लेखा Offline '));const runtime=new LocalRuntime({dataDir:dir,packaged:false});
  const root=path.resolve(__dirname,'..');const signing=crypto.createPrivateKey(fs.readFileSync(path.join(root,'.runtime','offline-signing.pem')));
  const now=new Date(),today=now.toLocaleDateString('en-CA',{timeZone:'Asia/Kolkata'});const expiry=new Date(now.getTime()+30*86400000).toLocaleDateString('en-CA',{timeZone:'Asia/Kolkata'});
  const body=Buffer.from(JSON.stringify({v:2,installation:runtime.id,customer:crypto.randomUUID(),company:'Offline Verification Company',email:'verification@example.test',starts:today,expires:expiry,issued:now.toISOString()}));const key='SB2.'+body.toString('base64url')+'.'+crypto.sign(null,body,signing).toString('base64url');
  let origin,jar={};
  async function request(route,{method='GET',payload,capability=true}={}){
    const headers={'Cookie':Object.entries(jar).map(([k,v])=>k+'='+v).join('; '),'Origin':origin};if(capability)headers['X-SimpleBooks-Local']=runtime.token;
    if(payload){headers['Content-Type']='application/json';headers['X-CSRFToken']=jar.csrftoken;headers['Idempotency-Key']=crypto.randomUUID();}
    const response=await fetch(origin+route,{method,headers,body:payload?JSON.stringify(payload):undefined,redirect:'manual'});
    for(const cookie of response.headers.getSetCookie()){const [name,value]=cookie.split(';')[0].split('=');jar[name]=value;}return response;
  }
  async function post(route,payload,status=201){const result=await request(route,{method:'POST',payload});const data=await result.json();assert.equal(result.status,status,JSON.stringify(data));return data;}
  try{
    origin=await runtime.start();assert.equal(new URL(origin).hostname,'127.0.0.1');assert.equal((await request('/',{capability:false})).status,403);
    assert.equal((await request('/admin/')).status,404);assert.equal((await request('/static/books/app.js')).status,200);
    await request('/activate/');assert.equal((await request('/api/activation/',{method:'POST'})).status,403);await post('/api/activation/',{key},200);
    const boot=await(await request('/api/bootstrap/')).json();assert.equal(boot.workspace.name,'Offline Verification Company');assert.equal(boot.subscription.can_write,true);
    const cash=boot.default_cash.id;const expense=boot.accounts.find(a=>a.name==='General expenses').id;
    const customer=await post('/api/masters/accounts/',{name:'Customer',kind:'customer'}),supplier=await post('/api/masters/accounts/',{name:'Supplier',kind:'supplier'}),item=await post('/api/masters/items/',{name:'Rice',unit:'kg'});
    const ids=[];
    const opening=await post('/api/vouchers/',{kind:'OPN',date:today,balances:[{account:cash,side:'debit',amount:'100'}],lines:[],expected_total:'100'});ids.push(opening.id);
    const payment=await post('/api/vouchers/',{kind:'PAY',date:today,account:expense,cash_account:cash,amount:'10.10',expected_total:'10.10',narration:'Offline payment'});ids.push(payment.id);
    const receipt=await post('/api/vouchers/',{kind:'REC',date:today,account:customer.id,cash_account:cash,amount:'10.10',expected_total:'10.10',narration:'Offline receipt'});ids.push(receipt.id);
    const purchase=await post('/api/vouchers/',{kind:'PUR',date:today,account:supplier.id,lines:[{item:item.id,quantity:'10',rate:'100'}],expected_total:'1000',narration:''});ids.push(purchase.id);
    const sale=await post('/api/vouchers/',{kind:'SAL',date:today,account:customer.id,lines:[{item:item.id,quantity:'2',rate:'150'}],expected_total:'300',narration:''});ids.push(sale.id);
    const cn=await post('/api/vouchers/',{kind:'CN',date:today,account:customer.id,reference:sale.id,lines:[{item:item.id,quantity:'1',rate:'150'}],expected_total:'150',narration:''});ids.push(cn.id);
    const dn=await post('/api/vouchers/',{kind:'DN',date:today,account:supplier.id,reference:purchase.id,lines:[{item:item.id,quantity:'1',rate:'100'}],expected_total:'100',narration:''});ids.push(dn.id);
    const reverse=await post('/api/vouchers/'+payment.id+'/reverse/',{version:1,date:today,reason:'Cancelled'},200);ids.push(reverse.id);
    await post('/api/vouchers/',{kind:'SAL',date:today,account:customer.id,lines:[{item:item.id,quantity:'999',rate:'150'}],expected_total:'149850',narration:''},400);
    for(const id of ids){const response=await request('/api/vouchers/'+id+'/pdf/');assert.equal(response.status,200);assert.equal(Buffer.from(await response.arrayBuffer()).subarray(0,5).toString(),'%PDF-');}
    const stock=await(await request('/api/inventory/?item='+item.id)).json();assert.equal(stock.closing.quantity,'8.000');assert.equal(stock.closing.value,'800.00');
    const company=await request('/company/');assert.equal(company.status,200);
    const backup=path.join(dir,'manual.sqlite3');await runtime.fileAction('backup',backup);assert.ok(fs.statSync(backup).size>0);
    await runtime.fileAction('backup',backup); // Replacing an existing export must work on Windows too.
    const savedOrigin=origin;
    const socket=require('node:net').createConnection({host:'127.0.0.1',port:Number(new URL(origin).port)});
    await new Promise((resolve,reject)=>{socket.once('error',reject);socket.once('data',resolve);socket.once('connect',()=>socket.write('GET /activate/ HTTP/1.1\r\nHost: '+new URL(origin).host+'\r\nConnection: keep-alive\r\nX-SimpleBooks-Local: '+runtime.token+'\r\n\r\n'));});
    const stopping=Date.now();await runtime.stop();socket.destroy();assert.ok(Date.now()-stopping<10000,'Idle browser channels must not delay shutdown');
    jar={};origin=await runtime.start();assert.equal(origin,savedOrigin);await request('/activate/');await post('/api/local/resume/',{},200);
    assert.equal((await(await request('/api/vouchers/')).json()).count,8);
    await runtime.stop();await runtime.fileAction('restore',backup);origin=await runtime.start();jar={};await request('/activate/');await post('/api/local/resume/',{},200);assert.equal((await(await request('/api/vouchers/')).json()).count,8);
    fs.writeFileSync(path.join(dir,'bad.sqlite3'),'not a backup');await assert.rejects(runtime.fileAction('restore',path.join(dir,'bad.sqlite3')));
  }finally{await runtime.stop();fs.rmSync(dir,{recursive:true,force:true});}
});
