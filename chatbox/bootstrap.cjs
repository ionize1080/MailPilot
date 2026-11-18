'use strict'
const { app, ipcMain } = require('electron')
const path = require('node:path')
const fs = require('node:fs')

const root = path.resolve(__dirname, '..')
const home = process.env.MAILPILOT_HOME || path.join(process.env.LOCALAPPDATA, 'MailPilot')
const source = process.env.MAILPILOT_SOURCE === 'graph' ? 'graph' : 'classic'
const profile = process.env.MAILPILOT_CHAT_DIR || path.join(home, 'Chatbox', source)
fs.mkdirSync(profile, { recursive: true })
app.setPath('userData', profile)
app.setName('Chatbox')
Object.defineProperty(app, 'isPackaged', { get: () => true })
Object.defineProperty(process, 'resourcesPath', { value: path.join(__dirname, 'resources') })
app.setAsDefaultProtocolClient = () => false

// The CE provider, fetch adapter and proxy retain full control of request headers.
// Chatbox's productName and version supply Electron's default browser identity.
function withMailServer(saved = {}) {
  const mcp = saved.mcp || {}
  const others = (mcp.servers || []).filter(server => server.id !== 'mailpilot')
  return { language: 'zh-Hans', ...saved, autoUpdate: false,
    mcp: { ...mcp, enabledBuiltinServers: mcp.enabledBuiltinServers || [], servers: [...others, {
      id: 'mailpilot', name: 'MailPilot', enabled: true,
      transport: { type: 'stdio', command: path.join(root, 'Runtime', 'python.exe'),
        args: ['-B', path.join(root, 'engine', 'service.py'), '--mcp'],
        env: { MAILPILOT_HOME: home, MAILPILOT_SOURCE: source, LOCALAPPDATA: process.env.LOCALAPPDATA,
          APPDATA: process.env.APPDATA, SYSTEMROOT: process.env.SystemRoot, TEMP: process.env.TEMP } }
    }] } }
}
const register = ipcMain.handle.bind(ipcMain)
ipcMain.handle = (name, handler) => {
  if (name === 'getSettings') return register(name, async (...args) => withMailServer(await handler(...args)))
  if (name === 'getStoreValue') return register(name, async (e, key, ...args) => {
    const result = await handler(e, key, ...args)
    return key === 'settings' ? withMailServer(result) : result
  })
  if (name === 'install-update' || name === 'ensureAutoLaunch') return register(name, () => false)
  return register(name, handler)
}
app.on('browser-window-created', (_e, win) => {
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith('file:')) e.preventDefault() })
})
app.on('window-all-closed', () => app.quit())
require('./dist/main/main.js')
