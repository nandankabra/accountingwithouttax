'use strict';
// Inspect the built Windows payload on the build host; this does not execute Windows.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),desktop=path.join(root,'desktop'),output=path.join(root,'output/desktop');
const sha=buffer=>crypto.createHash('sha256').update(buffer).digest('hex');
function files(directory){return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{const name=path.join(directory,entry.name);return entry.isDirectory()?files(name):[name];});}
function machine(filename){const buffer=fs.readFileSync(filename);assert.equal(buffer.subarray(0,2).toString(),'MZ',filename);const pe=buffer.readUInt32LE(60);assert.equal(buffer.subarray(pe,pe+4).toString(),'PE\0\0');return buffer.readUInt16LE(pe+4);}
(async()=>{
  const asar=await import(path.join(desktop,'node_modules/@electron/asar/lib/asar.js'));
  const archive=path.join(output,'win-unpacked/resources/app.asar'),executable=path.join(output,'win-unpacked/Simple Books.exe');
  const entries=asar.listPackage(archive).filter(name=>name!=='/assets');
  const expected=['/assets/icon.png','/main.cjs','/local_runtime.cjs','/policy.cjs','/preload.cjs','/setup.cjs','/setup.css','/setup.html','/package.json'];
  assert.deepEqual(entries.sort(),expected.sort());
  for(const name of entries.filter(name=>name!=='/package.json'))assert.ok(fs.readFileSync(path.join(desktop,name)).equals(asar.extractFile(archive,name.slice(1))),name+' differs from source');
  const pkg=JSON.parse(asar.extractFile(archive,'package.json'));assert.equal(pkg.version,'0.4.0');assert.equal(pkg.main,'main.cjs');assert.ok(!pkg.devDependencies);
  const headerHash=sha(Buffer.from(asar.getRawHeader(archive).headerString));assert.ok(fs.readFileSync(executable).includes(Buffer.from(headerHash)),'Missing matching embedded ASAR header integrity hash');
  const fuses=await require(path.join(desktop,'node_modules/@electron/fuses')).getCurrentFuseWire(executable);
  for(const index of [0,2,3])assert.equal(fuses[index],48);for(const index of [1,4,5])assert.equal(fuses[index],49);
  assert.equal(machine(executable),0x8664);
  const resources=path.join(output,'win-unpacked/resources'),backend=path.join(resources,'backend');
  const inventory=files(backend);const privateKey=fs.readFileSync(path.join(root,'.runtime/offline-signing.pem'));
  for(const filename of inventory){
    const relative=path.relative(backend,filename);assert.ok(!/\.sqlite3$|\.env$|offline-signing\.pem$|secret\.key$|__pycache__|(^|[/\\])test[^/\\]*\.py$|sqlite_test/.test(relative),relative+' must not be shipped');
    const payload=fs.readFileSync(filename);assert.ok(!payload.includes(privateKey),'Private issuer key found in client payload');
    const staged=path.join(root,'tmp/windows-local/backend',relative);assert.ok(payload.equals(fs.readFileSync(staged)),relative+' differs from staged payload');
    if(fs.existsSync(path.join(root,relative)))assert.ok(payload.equals(fs.readFileSync(path.join(root,relative))),relative+' differs from current source');
  }
  const binaries=files(path.join(resources,'python')).filter(filename=>/\.(exe|dll|pyd)$/i.test(filename));for(const filename of binaries)assert.equal(machine(filename),0x8664,filename+' is not x64');
  const runtime=JSON.parse(fs.readFileSync(path.join(resources,'runtime-manifest.json')));assert.equal(sha(fs.readFileSync(path.join(backend,'config/offline-public.pem'))),runtime.public_key_sha256);
  const installer=path.join(output,'SimpleBooks-Local-Setup-0.4.0-x64.exe');assert.ok(fs.statSync(installer).size>100000000);machine(installer);
  const report={version:'0.4.0',checkedAt:new Date().toISOString(),installer:path.basename(installer),bytes:fs.statSync(installer).size,sha256:sha(fs.readFileSync(installer)),payloadSourceMatches:true,noCustomerDataOrPrivateKey:true,backendFiles:inventory.length,windowsX64Binaries:binaries.length,asarHeaderHash:headerHash,fuses,runtime,windowsExecutionVerified:false,publisherSigned:false};
  fs.writeFileSync(path.join(root,'.runtime/windows-local-payload-verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({version:report.version,bytes:report.bytes,sha256:report.sha256,backendFiles:report.backendFiles,windowsX64Binaries:report.windowsX64Binaries,payloadSourceMatches:true,noCustomerDataOrPrivateKey:true,windowsExecutionVerified:false},null,2));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
