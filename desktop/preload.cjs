'use strict'
const { contextBridge, ipcRenderer } = require('electron')
const api = {}
for (const name of [
  'init',
  'window',
  'launch',
  'save',
  'directory',
  'login',
  'mail',
  'read',
  'link',
  'images',
]) {
  api[name] = (...args) => ipcRenderer.invoke('mailpilot:' + name, ...args)
}
api.on = (name, callback) => {
  if (!['message', 'layout', 'settings'].includes(name)) return
  const listener = (_e, value) => callback(value)
  ipcRenderer.on('mailpilot:' + name, listener)
  return () => ipcRenderer.off('mailpilot:' + name, listener)
}
contextBridge.exposeInMainWorld('mailpilot', api)
