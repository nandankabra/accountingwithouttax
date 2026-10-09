'use strict';
window.simpleBooks.installation().then(id=>{document.getElementById('installation').value=id||'Unavailable';});
document.getElementById('existing').addEventListener('click',async()=>{try{const result=await window.simpleBooks.resume();document.getElementById('error').textContent=result.error||'';}catch{document.getElementById('error').textContent='Could not open saved books. Restart the app.';}});
document.getElementById('connect').addEventListener('submit',async event=>{
  event.preventDefault();const button=document.getElementById('activate'),error=document.getElementById('error');button.disabled=true;button.textContent='Activating…';error.textContent='';
  try{const result=await window.simpleBooks.activate(document.getElementById('key').value);if(result.error)error.textContent=result.error;}
  catch{error.textContent='Could not activate. Contact your administrator.';}
  finally{button.disabled=false;button.textContent='Activate & open books →';}
});
