'use strict';
const {contextBridge,ipcRenderer}=require('electron');
if(window.location.protocol==='file:'&&window.location.pathname.endsWith('/setup.html'))contextBridge.exposeInMainWorld('simpleBooks',Object.freeze({activate:key=>ipcRenderer.invoke('subscription:activate',key)}));
