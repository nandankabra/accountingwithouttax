'use strict';
function serverOrigin(value){const url=new URL(value);if(url.username||url.password||url.search||url.hash||url.pathname!=='/')throw new Error('Use the server origin only, without paths or credentials.');const local=['localhost','127.0.0.1','[::1]'].includes(url.hostname);if(url.protocol!=='https:'&&!(url.protocol==='http:'&&local))throw new Error('Use HTTPS. HTTP is allowed only for a server on this PC.');return url.origin;}
function whatsapp(value){try{const url=new URL(value);return url.protocol==='https:'&&url.hostname==='wa.me'&&!url.username&&!url.password;}catch{return false;}}
function subscriptionKey(value){
  if(typeof value!=='string'||value.length>2000)throw new Error('Enter a valid subscription key.');
  value=value.trim();if(!/^SB1\.[A-Za-z0-9_-]+$/.test(value))throw new Error('Enter the key supplied by your administrator.');
  let packet;try{packet=JSON.parse(Buffer.from(value.slice(4),'base64url').toString('utf8'));}catch{throw new Error('Enter a valid subscription key.');}
  if(!packet||Object.keys(packet).sort().join(',')!=='origin,token'||typeof packet.token!=='string'||!/^[A-Za-z0-9_-]{43}$/.test(packet.token))throw new Error('Enter a valid subscription key.');
  return {origin:serverOrigin(packet.origin),key:value};
}
function offlineKey(value){if(typeof value!=='string'||value.length>4000||!/^SB2\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{86}$/.test(value.trim()))throw Error('Enter the offline Windows subscription key supplied by your provider.');return value.trim();}
module.exports={serverOrigin,whatsapp,subscriptionKey,offlineKey};
