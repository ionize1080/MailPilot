'use strict'
const { app, BrowserWindow, ipcMain, dialog, nativeTheme, shell, session } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')
const prefs = require('./preferences.cjs')
const MailWorker = require('./worker.cjs')
const { WindowLayout, pane } = require('./window-layout.cjs')

app.setPath('userData', path.join(prefs.home, 'Desktop'))
app.setName('MailPilot')
const views = new Map(),
  workers = new Map(),
  chats = new Map()
const titles = { search: '正则查找', settings: '设置', reader: '邮件详情' }
const launch = { action: process.argv[2] || 'search', source: process.env.MAILPILOT_SOURCE }
const pending = []
let cfg
function alertError(e) {
  dialog.showErrorBox('MailPilot', e.message || String(e))
}
function maybeQuit() {
  if (!views.size && !chats.size) app.quit()
}
function worker(source) {
  if (!workers.has(source) || workers.get(source).closed) workers.set(source, new MailWorker(source))
  return workers.get(source)
}
function releaseWorkers() {
  for (const [source, process] of workers) {
    if (![...views.values()].some((v) => v.source === source && v.page !== 'settings')) {
      process.close()
      workers.delete(source)
    }
  }
}
function theme() {
  nativeTheme.themeSource = cfg.theme === 'paper' ? 'light' : cfg.theme
}
function notify(v, topic, data) {
  if (!v.win.isDestroyed()) v.win.webContents.send('mailpilot:' + topic, data)
}
function settings(patch) {
  const previous = cfg
  cfg = prefs.save(patch)
  theme()
  const indexChanged = ['indexDir', 'storeScope', 'clientId'].some((k) => previous[k] !== cfg[k])
  for (const [source, proc] of workers) {
    if (indexChanged) {
      proc.close()
      workers.delete(source)
    }
  }
  for (const v of [...views.values()]) {
    const switchSource = v.followDefault && previous.source !== cfg.source
    if (v.page === 'reader' && (indexChanged || switchSource)) {
      v.win.close()
      continue
    }
    if (switchSource) {
      v.source = cfg.source
      if (v.layout) v.layout.source = v.source
    }
    notify(v, 'settings', { cfg, source: v.source, reset: indexChanged || switchSource })
    if (v.layout) v.layout.apply(cfg, switchSource).catch(alertError)
  }
  releaseWorkers()
  if (previous.palette !== cfg.palette) pane('icons', 'search', '0', 'right', 420)
  return cfg
}
function view(page, source, followDefault = false, query = null) {
  let v = [...views.values()].find((v) => v.page === page && (page === 'settings' || v.source === source))
  if (v) {
    if (page === 'settings') {
      v.source = source
      v.followDefault = followDefault
    }
    if (v.win.isMinimized()) v.win.restore()
    if (query) {
      v.query = query
      notify(v, 'message', query)
    }
    if (v.layout) v.layout.apply(cfg, true).catch(alertError)
    else {
      v.win.show()
      v.win.focus()
    }
    return v
  }
  const sizes = {
    search: [1020, 720, 480, 390],
    settings: [930, 730, 540, 420],
    reader: [900, 780, 420, 360],
  }
  const [width, height, minWidth, minHeight] = sizes[page]
  const win = new BrowserWindow({
    width,
    height,
    minWidth,
    minHeight,
    show: false,
    frame: false,
    title: 'MailPilot · ' + titles[page],
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#192333' : '#f7faf8',
    icon: path.join(__dirname, 'icons/mailpilot.ico'),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: false,
      spellcheck: false,
    },
  })
  v = { page, source, followDefault, query, win }
  views.set(win.webContents.id, v)
  const id = win.webContents.id
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (e) => e.preventDefault())
  win.webContents.on('will-frame-navigate', (e, details) => {
    if (!details?.isMainFrame && !['about:blank', 'about:srcdoc'].includes(details?.url || e.url))
      e.preventDefault()
  })
  if (page === 'search')
    v.layout = new WindowLayout(win, 'search', source, (mode) => notify(v, 'layout', mode))
  win.once('ready-to-show', () => {
    if (v.layout) v.layout.apply(cfg, true).catch(alertError)
    else win.show()
  })
  win.on('closed', () => {
    views.delete(id)
    releaseWorkers()
    maybeQuit()
  })
  win.loadFile(path.join(__dirname, page + '.html')).catch(alertError)
  return v
}
function openAI(source) {
  if (source === 'graph' && !fs.existsSync(path.join(prefs.home, 'graph-account.json'))) {
    view('settings', source)
    throw Error('请先在「邮箱与索引」中连接 Microsoft 邮箱')
  }
  const active = chats.get(source)
  if (active?.connected) {
    active.send({ action: 'show' })
    return
  }
  const child = spawn(process.execPath, [path.join(prefs.root, 'Chatbox')], {
    cwd: prefs.root,
    stdio: ['ignore', 'ignore', 'ignore', 'ipc'],
    env: { ...process.env, MAILPILOT_SOURCE: source, MAILPILOT_CHAT_DIR: path.join(cfg.chatDir, source) },
  })
  chats.set(source, child)
  child.on('message', (msg) => {
    if (msg?.action === 'layout' && ['window', 'sidebar'].includes(msg.layout))
      settings({ aiLayout: msg.layout })
  })
  child.on('error', alertError)
  child.on('close', () => {
    if (chats.get(source) === child) chats.delete(source)
    maybeQuit()
  })
}
function route({ action, source }) {
  const follow = !['classic', 'graph'].includes(source)
  if (follow) source = cfg.source
  if (action === 'ai') openAI(source)
  else if (action === 'search' || action === 'settings') view(action, source, follow)
  else if (action === 'ai-window' || action === 'ai-sidebar') {
    settings({ aiLayout: action.slice(3) })
    maybeQuit()
  }
}
function handle(name, pages, fn) {
  ipcMain.handle('mailpilot:' + name, (event, ...args) => {
    const v = views.get(event.sender.id)
    if (!v || event.senderFrame !== event.sender.mainFrame || !pages.includes(v.page))
      throw Error('无法访问此操作')
    return fn(v, ...args)
  })
}
const all = ['search', 'settings', 'reader']
handle('init', all, (v) => ({
  cfg,
  defaults: prefs.defaults,
  source: v.source,
  page: v.page,
  query: v.query,
  layout: v.layout?.mode || 'window',
}))
handle('window', all, (v, action) => {
  if (action === 'close') v.win.close()
  if (action === 'minimize') return v.layout ? v.layout.collapse() : v.win.minimize()
  if (action === 'maximize' && (!v.layout || v.layout.mode === 'window'))
    v.win.isMaximized() ? v.win.unmaximize() : v.win.maximize()
  if (action === 'dock' && v.layout)
    return settings({ searchLayout: v.layout.mode === 'window' ? 'sidebar' : 'window' })
})
handle('launch', all, (v, action) => {
  if (action === 'ai') return openAI(v.source)
  if (action === 'settings' || action === 'search') view(action, v.source, v.followDefault)
})
handle('save', ['settings'], (_v, patch) => settings(patch))
handle('directory', ['settings'], async (v, current) => {
  const result = await dialog.showOpenDialog(v.win, {
    defaultPath: current,
    properties: ['openDirectory', 'createDirectory'],
  })
  return result.canceled ? '' : result.filePaths[0]
})
handle(
  'login',
  ['settings'],
  () =>
    new Promise((resolve, reject) => {
      if (!cfg.clientId) return reject(Error('请先填写 Microsoft 应用 ID'))
      const child = spawn(
        path.join(prefs.root, 'Runtime/python.exe'),
        ['-B', path.join(prefs.root, 'engine/service.py'), '--login'],
        { stdio: 'ignore', windowsHide: true }
      )
      child.on('error', reject)
      child.on('exit', (code) => (code === 0 ? resolve(true) : reject(Error('邮箱连接未完成'))))
    })
)
handle('mail', ['search', 'reader'], (v, name, args) => {
  const allowed =
    v.page === 'reader'
      ? ['detail', 'preview_marks', 'open']
      : ['search_mail', 'index_status', 'list_folders', 'refresh', 'pause', 'auto', 'open']
  if (!allowed.includes(name)) throw Error('未知操作')
  return worker(v.source).call(name, args)
})
handle('read', ['search'], (v, args) => {
  view('reader', v.source, v.followDefault, args)
})
handle('images', ['reader'], (v, allow) => {
  v.externalImages = allow === true
})
handle('link', ['reader'], (_v, link) => {
  const url = new URL(link)
  if (['https:', 'http:', 'mailto:'].includes(url.protocol)) return shell.openExternal(url.href)
})
if (!app.requestSingleInstanceLock(launch)) app.quit()
else {
  app.on('second-instance', (_e, _argv, _cwd, data) => {
    if (cfg) {
      try {
        route(data)
      } catch (e) {
        alertError(e)
      }
    } else pending.push(data)
  })
  app.on('window-all-closed', maybeQuit)
  app
    .whenReady()
    .then(() => {
      cfg = prefs.read()
      theme()
      session.defaultSession.setPermissionRequestHandler((_wc, _perm, done) => done(false))
      session.defaultSession.webRequest.onBeforeRequest(
        { urls: ['http://*/*', 'https://*/*'] },
        (details, done) => {
          const reader = views.get(details.webContentsId)
          done({
            cancel: !(reader?.page === 'reader' && reader.externalImages && details.resourceType === 'image'),
          })
        }
      )
      route(launch)
      pending.splice(0).forEach(route)
    })
    .catch(alertError)
}
