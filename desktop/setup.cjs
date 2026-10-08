'use strict';
document.getElementById('connect').addEventListener('submit',async event=>{
  event.preventDefault();const button=document.getElementById('activate'),error=document.getElementById('error');button.disabled=true;button.textContent='Activating…';error.textContent='';
  try{const result=await window.simpleBooks.activate(document.getElementById('key').value);if(result.error)error.textContent=result.error;}
  catch{error.textContent='Could not activate. Contact your administrator.';}
  finally{button.disabled=false;button.textContent='Activate & open books →';}
});
