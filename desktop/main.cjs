'use strict';
const {app,BrowserWindow,session,shell,dialog,Menu,ipcMain}=require('electron');
const fs=require('node:fs');const path=require('node:path');const {pathToFileURL}=require('node:url');
const {serverOrigin,whatsapp,subscriptionKey}=require('./policy.cjs');let window,origin;
app.setName('Simple Books');app.setPath('userData',process.env.SIMPLEBOOKS_USER_DATA_DIR||path.join(app.getPath('appData'),'SimpleBooks'));
app.setAppUserModelId('in.simplebooks.desktop');
const configPath=()=>path.join(app.getPath('userData'),'server.json');
function openServer(){window.loadURL(origin).catch(()=>{});}
function setup(){window.loadFile(path.join(__dirname,'setup.html'));}
const setupUrl=pathToFileURL(path.join(__dirname,'setup.html')).href;
app.whenReady().then(()=>{
  session.defaultSession.setPermissionRequestHandler((contents,permission,callback)=>callback(false));session.defaultSession.setPermissionCheckHandler(()=>false);
  window=new BrowserWindow({width:1280,height:860,minWidth:390,minHeight:600,title:'Simple Books',icon:path.join(__dirname,'assets/icon.png'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  let activating=false;
  ipcMain.handle('subscription:activate',async(event,value)=>{
    if(event.sender!==window.webContents||event.senderFrame?.url!==setupUrl)return {error:'Activation is only available in the subscription screen.'};
    if(activating)return {error:'Activation is already in progress.'};activating=true;
    try{
      const parsed=subscriptionKey(value),target=parsed.origin;
      const first=await session.defaultSession.fetch(target+'/activate/',{credentials:'include',redirect:'error'});
      if(!first.ok)throw new Error('Could not reach the activation service. Contact your administrator.');
      await first.text();
      const cookies=await session.defaultSession.cookies.get({url:target,name:'csrftoken'});
      if(!cookies.length)throw new Error('Could not establish a secure activation session.');
      const response=await session.defaultSession.fetch(target+'/api/activation/',{method:'POST',credentials:'include',redirect:'error',headers:{'Content-Type':'application/json','X-CSRFToken':cookies[0].value,'Origin':target},body:JSON.stringify({key:parsed.key})});
      let result;try{result=await response.json();}catch{throw new Error('The server returned an invalid activation response.');}
      if(!response.ok||!result.activated)throw new Error(result.error||'Activation failed. Contact your administrator.');
      origin=target;fs.writeFileSync(configPath(),JSON.stringify({origin}),{mode:0o600});await session.defaultSession.cookies.flushStore();openServer();return {activated:true};
    }catch(error){return {error:error.message||'Could not activate. Check your internet connection.'};}finally{activating=false;}
  });
  window.webContents.on('will-navigate',(event,url)=>{
    try{if(new URL(url).origin!==origin){event.preventDefault();if(whatsapp(url))shell.openExternal(url);}}catch{event.preventDefault();}
  });
  window.webContents.setWindowOpenHandler(({url})=>{if(whatsapp(url))shell.openExternal(url);return {action:'deny'};});
  window.webContents.on('will-redirect',(event,url)=>{try{if(new URL(url).origin!==origin)event.preventDefault();}catch{event.preventDefault();}});
  session.defaultSession.on('will-download',(event,item)=>{try{if(new URL(item.getURL()).origin!==origin){event.preventDefault();return;}}catch{event.preventDefault();return;}item.setSaveDialogOptions({title:'Save voucher or report',defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});});
  window.webContents.on('did-fail-load',(event,code,description,url,isMainFrame)=>{if(isMainFrame&&code!==-3)dialog.showMessageBox(window,{type:'warning',title:'Server unavailable',message:'Could not connect to your accounting server.',detail:'Check your internet connection or contact your administrator. Saved vouchers remain on the server; local drafts are retained.',buttons:['Retry','Subscription key']}).then(({response})=>response===0&&origin?openServer():setup());});
  Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'Simple Books',submenu:[{label:'Reload books',click:()=>window.reload()},{label:'Enter subscription key',click:()=>dialog.showMessageBox(window,{type:'question',message:'Open subscription activation?',detail:'Save any unsaved form first. Existing drafts remain stored for this company.',buttons:['Cancel','Continue'],defaultId:0,cancelId:0}).then(({response})=>{if(response===1)setup();})},{type:'separator'},{role:'quit'}]}]));
  try{origin=serverOrigin(JSON.parse(fs.readFileSync(configPath(),'utf8')).origin);openServer();}catch{setup();}
});
app.on('window-all-closed',()=>app.quit());
