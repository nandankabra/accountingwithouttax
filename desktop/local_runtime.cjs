'use strict';
const {spawn}=require('node:child_process');const fs=require('node:fs');const path=require('node:path');const readline=require('node:readline');const crypto=require('node:crypto');
function installation(dataDir){
  const filename=path.join(dataDir,'installation.json');fs.mkdirSync(dataDir,{recursive:true});
  try{const id=JSON.parse(fs.readFileSync(filename,'utf8')).id;if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id))throw Error();return id;}
  catch(error){if(error.code!=='ENOENT')throw Error('Installation details are damaged. Restore installation.json or contact your provider.');const id=crypto.randomUUID();fs.writeFileSync(filename,JSON.stringify({id}),{mode:0o600,flag:'wx'});return id;}
}
class LocalRuntime{
  constructor({dataDir,resources,packaged,python}){
    this.dataDir=dataDir;this.id=installation(dataDir);this.token=crypto.randomBytes(32).toString('hex');
    this.root=packaged?path.join(resources,'backend'):path.resolve(__dirname,'..');
    this.python=packaged?path.join(resources,'python','python.exe'):(python||path.join(this.root,'.venv',...(process.platform==='win32'?['Scripts','python.exe']:['bin','python'])));
    this.script=path.join(this.root,'desktop','local_server.py');this.publicKey=packaged?path.join(this.root,'config','offline-public.pem'):path.join(this.root,'.runtime','offline-public.pem');
  }
  spawn(action='serve',filename){
    const env={...process.env,PYTHONUNBUFFERED:'1',PYTHONDONTWRITEBYTECODE:'1'};for(const key of ['PYTHONHOME','PYTHONPATH','ELECTRON_RUN_AS_NODE','DJANGO_SETTINGS_MODULE','SIMPLEBOOKS_SIGNING_KEY'])delete env[key];
    const child=spawn(this.python,['-X','utf8','-u',this.script],{cwd:this.root,env,windowsHide:true,stdio:['pipe','pipe','pipe']});child.stdin.on('error',()=>{});
    child.stdin.write(JSON.stringify({action,path:filename,data_dir:this.dataDir,installation:this.id,token:this.token,public_key:this.publicKey})+'\n');return child;
  }
  async start(){
    if(this.child)throw Error('The local service is already running.');const child=this.spawn();this.child=child;
    child.stderr.on('data',data=>fs.appendFileSync(path.join(this.dataDir,'service.log'),data));
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{child.kill();reject(Error('Local books could not start within 90 seconds. See service.log in the data folder.'));},90000);
      readline.createInterface({input:child.stdout}).on('line',line=>{try{const state=JSON.parse(line);if(state.ready){clearTimeout(timer);this.origin=state.origin;resolve(this.origin);}}catch{}});
      child.once('error',error=>{clearTimeout(timer);this.child=null;reject(Error('Could not start the accounting engine: '+error.message));});
      child.once('exit',code=>{clearTimeout(timer);this.child=null;if(!this.origin)reject(Error('The local accounting engine failed to start. See service.log in the data folder.'));else if(!this.stopping)this.onFailure?.(code);});
    });
  }
  async stop(){
    const child=this.child;if(!child)return;this.stopping=true;
    await new Promise(resolve=>{const timer=setTimeout(()=>child.kill(),35000);child.once('exit',()=>{clearTimeout(timer);resolve();});child.stdin.end();});this.origin=null;this.stopping=false;
  }
  async fileAction(action,filename){
    const child=this.spawn(action,filename);child.stdin.end();let output='',error='';child.stdout.on('data',chunk=>output+=chunk);child.stderr.on('data',chunk=>error+=chunk);
    return new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',code=>{if(code===0){try{resolve(JSON.parse(output));}catch{reject(Error('Invalid backup service response.'));}}else reject(Error('The '+action+' could not be completed. '+error.split('\n').filter(Boolean).slice(-1).join('')));});});
  }
}
module.exports={LocalRuntime,installation};
