const test=require('node:test');const assert=require('node:assert/strict');const {serverOrigin,whatsapp}=require('./policy.cjs');
test('server origins allow TLS and loopback only',()=>{assert.equal(serverOrigin('https://books.example.test'),'https://books.example.test');assert.equal(serverOrigin('http://127.0.0.1:8017'),'http://127.0.0.1:8017');for(const value of ['http://remote.example.test','https://user:password@books.example.test','file:///tmp/secret','javascript:alert(1)','https://books.example.test/private?token=secret'])assert.throws(()=>serverOrigin(value));});
test('only WhatsApp HTTPS links may leave the app',()=>{assert.equal(whatsapp('https://wa.me/919876543210?text=hello'),true);for(const value of ['https://wa.me.evil.test','http://wa.me/123','file:///tmp/x','https://evil@wa.me/123'])assert.equal(whatsapp(value),false);});
test('subscription keys carry a validated server and secret without exposing malformed values',()=>{
  const {subscriptionKey}=require('./policy.cjs');
  const key=(packet)=>'SB1.'+Buffer.from(JSON.stringify(packet)).toString('base64url');
  const value=key({origin:'https://books.example.com',token:'a'.repeat(43)});
  assert.deepEqual(subscriptionKey(value),{origin:'https://books.example.com',key:value});
  for(const packet of [{origin:'http://untrusted.example.com',token:'a'.repeat(43)},{origin:'https://user:password@books.example.com',token:'a'.repeat(43)},{origin:'https://books.example.com',token:'short'},{origin:'https://books.example.com',token:'a'.repeat(43),extra:true}])assert.throws(()=>subscriptionKey(key(packet)));
  for(const value of [null,{},'secret-invalid','SB1.!!!','SB1.e30','SB1.'+'a'.repeat(2000)])assert.throws(()=>subscriptionKey(value));
});
