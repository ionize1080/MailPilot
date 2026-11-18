'use strict'
const { app, ipcMain, nativeTheme } = require('electron')
const { spawn } = require('node:child_process')
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
const preferences = require('../Desktop/preferences.cjs')
const { WindowLayout } = require('../Desktop/window-layout.cjs')
let panel, chatWindow
let current = preferences.read()
function applyLayout(reveal = false) {
  current = preferences.read()
  nativeTheme.themeSource = current.syncAiTheme && current.theme !== 'system' ? (current.theme === 'dark' ? 'dark' : 'light') : 'system'
  if (chatWindow && !chatWindow.isDestroyed()) {
    chatWindow.setIcon(path.join(root, 'Desktop/icons', current.palette + '-ai.png'))
    chatWindow.webContents.send('system-theme-updated')
  }
  if (panel) return panel.apply(current, reveal)
}
ipcMain.handle('mailpilot:appearance', event => {
  if (!chatWindow || event.sender !== chatWindow.webContents || event.senderFrame !== event.sender.mainFrame || !current.syncAiTheme) return null
  const base = { jade:['#23997d','#a2dfcc'], ocean:['#4671d6','#adc5ff'], graphite:['#515e6f','#c1cddc'] }
  const dark = nativeTheme.shouldUseDarkColors, colors = base[current.palette] || base.jade
  return { theme: dark ? 'dark' : 'light', accent: current.accentColor || colors[dark ? 1 : 0],
    background: current.theme === 'paper' ? '#fffdf8' : dark ? '#202e3b' : '#ffffff',
    secondary: current.theme === 'paper' ? '#f6f1e7' : dark ? '#192632' : '#f2f6f3' }
})
process.on('message', msg => {
  if (msg?.action === 'settings' || msg?.action === 'show') applyLayout(msg.action === 'show')
})
ipcMain.handle('mailpilot:panel', async (event, command) => {
  if (!panel || event.sender !== chatWindow.webContents || event.senderFrame !== event.sender.mainFrame) return 'window'
  if (command === 'toggle') {
    const layout = panel.mode === 'window' ? 'sidebar' : 'window'
    if (process.connected) process.send({ action: 'layout', layout })
    else spawn(process.execPath, [path.join(root, 'Desktop'), 'ai-' + layout], { detached: true, stdio: 'ignore' }).unref()
  }
  if (command === 'collapse') await panel.collapse()
  return panel.mode
})

// The CE provider, fetch adapter and proxy retain full control of request headers.
// Chatbox's productName and version supply Electron's default browser identity.
function withMailServer(saved = {}) {
  const mcp = saved.mcp || {}
  const others = (mcp.servers || []).filter(server => server.id !== 'mailpilot')
  const previous = (mcp.servers || []).find(server => server.id === 'mailpilot')
  return { language: 'zh-Hans', ...saved, autoUpdate: false,
    mcp: { ...mcp, enabledBuiltinServers: mcp.enabledBuiltinServers || [], servers: [...others, {
      id: 'mailpilot', name: 'MailPilot', enabled: previous?.enabled !== false,
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
  if (chatWindow) return
  chatWindow = win
  win.setIcon(path.join(root, 'Desktop/icons', current.palette + '-ai.png'))
  panel = new WindowLayout(win, 'ai', source, mode => {
    if (!win.isDestroyed()) win.webContents.send('mailpilot:layout', mode)
  })
  win.once('ready-to-show', () => setImmediate(() => applyLayout(true)))
  const watcher = fs.watch(home, (_type, name) => {
    if (name === 'settings.json') applyLayout()
  })
  win.on('closed', () => { watcher.close(); panel = null; chatWindow = null })
})
app.on('window-all-closed', () => app.quit())
require('./dist/main/main.js')
