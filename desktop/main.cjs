'use strict';
const {app,BrowserWindow,session,shell,dialog,Menu,ipcMain}=require('electron');const path=require('node:path');const {pathToFileURL}=require('node:url');
const {whatsapp,offlineKey}=require('./policy.cjs');const {LocalRuntime}=require('./local_runtime.cjs');
let window,origin,runtime,quitting=false,restoring=false;
app.setName('Simple Books');app.setPath('userData',process.env.SIMPLEBOOKS_USER_DATA_DIR||path.join(app.getPath('appData'),'SimpleBooksLocal'));app.setAppUserModelId('in.simplebooks.local');
const primary=app.requestSingleInstanceLock();if(!primary)app.quit();
app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});
const setupUrl=pathToFileURL(path.join(__dirname,'setup.html')).href;
function openBooks(){window.loadURL(origin).catch(()=>{});}function setup(){window.loadFile(path.join(__dirname,'setup.html'));}
async function callLocal(endpoint,payload){
  const ses=session.defaultSession;const first=await ses.fetch(origin+'/activate/',{credentials:'include',redirect:'error',signal:AbortSignal.timeout(20000)});
  if(!first.ok)throw Error('The local accounting service is unavailable. Restart the app.');await first.text();
  const cookies=await ses.cookies.get({url:origin,name:'csrftoken'});if(!cookies.length)throw Error('Could not establish the local session. Restart the app.');
  const response=await ses.fetch(origin+endpoint,{method:'POST',credentials:'include',redirect:'error',signal:AbortSignal.timeout(20000),headers:{'Content-Type':'application/json','X-CSRFToken':cookies[0].value,'Origin':origin},body:JSON.stringify(payload)});
  const result=await response.json();if(!response.ok)throw Error(result.error||'The operation could not be completed.');return result;
}
async function resume(){const result=await callLocal('/api/local/resume/',{});result.activated?openBooks():setup();}
async function backup(){
  const result=await dialog.showSaveDialog(window,{title:'Back up local company',defaultPath:path.join(app.getPath('documents'),'SimpleBooks-'+new Date().toISOString().slice(0,10)+'.sqlite3'),filters:[{name:'Simple Books backup',extensions:['sqlite3']}]});if(result.canceled)return;
  try{await runtime.fileAction('backup',result.filePath);await dialog.showMessageBox(window,{message:'Company backup saved.',detail:'Keep the backup and your installation ID on another drive.',type:'info'});}catch(error){dialog.showErrorBox('Backup failed',error.message);}
}
async function restore(){
  if(restoring)return;const selected=await dialog.showOpenDialog(window,{title:'Restore company backup',properties:['openFile'],filters:[{name:'Simple Books backup',extensions:['sqlite3']}]});if(selected.canceled)return;
  const confirm=await dialog.showMessageBox(window,{type:'question',message:'Replace this PC’s books with the selected backup?',detail:'Save unsaved forms first. Your current database will be backed up before replacement. A different installation requires a new subscription key.',buttons:['Cancel','Restore'],cancelId:0,defaultId:0});if(confirm.response!==1)return;
  restoring=true;setup();try{await runtime.stop();await runtime.fileAction('restore',selected.filePaths[0]);origin=await runtime.start();await resume();}catch(error){dialog.showErrorBox('Restore could not finish',error.message);if(!runtime.child){try{origin=await runtime.start();await resume();}catch{app.quit();}}}finally{restoring=false;}
}
app.whenReady().then(async()=>{
  if(!primary)return;if(app.isPackaged&&process.platform!=='win32'){dialog.showErrorBox('Unsupported package','This standalone release is packaged for Windows.');app.quit();return;}
  session.defaultSession.setPermissionRequestHandler((contents,permission,callback)=>callback(false));session.defaultSession.setPermissionCheckHandler(()=>false);
  window=new BrowserWindow({width:1280,height:860,minWidth:390,minHeight:600,title:'Simple Books',icon:path.join(__dirname,'assets/icon.png'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  runtime=new LocalRuntime({dataDir:app.getPath('userData'),resources:process.resourcesPath,packaged:app.isPackaged,python:process.env.SIMPLEBOOKS_DEV_PYTHON});
  session.defaultSession.webRequest.onBeforeSendHeaders((details,callback)=>{const headers={...details.requestHeaders};for(const name of Object.keys(headers))if(name.toLowerCase()==='x-simplebooks-local')delete headers[name];if(origin&&new URL(details.url).origin===origin)headers['X-SimpleBooks-Local']=runtime.token;callback({requestHeaders:headers});});
  let activating=false;
  ipcMain.handle('subscription:installation',event=>event.sender===window.webContents&&event.senderFrame?.url===setupUrl?runtime.id:null);
  ipcMain.handle('subscription:resume',async event=>{if(event.sender!==window.webContents||event.senderFrame?.url!==setupUrl)return {error:'Open the activation screen first.'};try{const result=await callLocal('/api/local/resume/',{});if(result.activated)openBooks();else return {error:'Enter a valid offline key to create your company.'};return result;}catch(error){return {error:error.message};}});
  ipcMain.handle('subscription:activate',async(event,value)=>{if(event.sender!==window.webContents||event.senderFrame?.url!==setupUrl)return {error:'Activation is only available in the subscription screen.'};if(activating||restoring)return {error:'Please wait for the current operation to finish.'};activating=true;
    try{const result=await callLocal('/api/activation/',{key:offlineKey(value)});await session.defaultSession.cookies.flushStore();openBooks();return result;}catch(error){return {error:error.name==='TimeoutError'?'The local service took too long. Restart the app and try again.':error.message};}finally{activating=false;}});
  window.webContents.on('will-navigate',(event,url)=>{try{if(new URL(url).origin!==origin){event.preventDefault();if(whatsapp(url))shell.openExternal(url);}}catch{event.preventDefault();}});
  window.webContents.setWindowOpenHandler(({url})=>{if(whatsapp(url))shell.openExternal(url);return {action:'deny'};});
  window.webContents.on('will-redirect',(event,url)=>{try{if(new URL(url).origin!==origin)event.preventDefault();}catch{event.preventDefault();}});
  session.defaultSession.on('will-download',(event,item)=>{try{if(new URL(item.getURL()).origin!==origin){event.preventDefault();return;}}catch{event.preventDefault();return;}item.setSaveDialogOptions({title:'Save voucher or report',defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});});
  window.webContents.on('did-fail-load',(event,code,description,url,isMainFrame)=>{if(isMainFrame&&code!==-3&&!quitting&&!restoring)dialog.showMessageBox(window,{type:'warning',title:'Local books unavailable',message:'Could not open the local books.',detail:'Restart the app. Your company data remains in the local data folder.',buttons:['Close'],cancelId:0}).then(()=>app.quit());});
  runtime.onFailure=()=>{if(!quitting&&!restoring){dialog.showErrorBox('Local engine stopped','Restart Simple Books. Your data is saved in the local data folder.');app.quit();}};
  Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'Simple Books',submenu:[{label:'Reload books',accelerator:'F5',click:()=>window.reload()},{label:'Enter / renew subscription key',click:()=>dialog.showMessageBox(window,{type:'question',message:'Open subscription activation?',detail:'Save any unsaved form first. Existing drafts remain on this PC.',buttons:['Cancel','Continue'],defaultId:0,cancelId:0}).then(({response})=>{if(response===1)setup();})},{type:'separator'},{label:'Back up company…',click:backup},{label:'Restore company backup…',click:restore},{label:'Open local data folder',click:()=>shell.openPath(app.getPath('userData'))},{type:'separator'},{role:'quit'}]}]));
  try{origin=await runtime.start();await resume();}catch(error){dialog.showErrorBox('Could not start Simple Books',error.message);app.quit();}
}).catch(error=>{dialog.showErrorBox('Could not start Simple Books',error.message);app.quit();});
app.on('before-quit',event=>{if(runtime?.child&&!quitting){event.preventDefault();quitting=true;runtime.stop().finally(()=>app.quit());}});app.on('window-all-closed',()=>app.quit());
