'use strict'
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path')
const { app, BrowserWindow, dialog } = require('electron')
const { execFileSync, spawn } = require('node:child_process')
const { createInterface } = require('node:readline')
const root = path.resolve(__dirname, '..'),
  bundle = process.env.MAILPILOT_QA_BUNDLE || path.join(root, 'dist/MailPilot'),
  home = process.env.MAILPILOT_HOME
assert(path.resolve(home).startsWith(path.join(root, '.build') + path.sep))
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const evalIn = (win, code) => win.webContents.executeJavaScript(code)
const paneStep = (message) => {
  if (process.env.MAILPILOT_EXPECT_PANE)
    fs.appendFileSync(path.join(home, 'pane.log'), new Date().toISOString() + ' ' + message + '\n')
}
async function until(fn, label) {
  let last
  for (let i = 0; i < 120; i++) {
    try {
      const result = await fn()
      if (result) return result
    } catch (e) {
      last = e
    }
    await wait(100)
  }
  throw Error('Timed out: ' + label + (last ? ' ' + last.message : ''))
}
const windows = () => BrowserWindow.getAllWindows()
const page = (name) =>
  until(() => windows().find((w) => w.webContents.getURL().endsWith('/' + name + '.html')), name)
const see = (win, js) => until(() => evalIn(win, 'Boolean(' + js + ')'), js)
async function checkPaneBounds(win) {
  const { dockWidth } = JSON.parse(fs.readFileSync(path.join(home, 'settings.json')))
  await until(() => {
    const { width, height } = win.getBounds()
    return win.isVisible() && width >= 250 && width <= dockWidth + 32 && height >= 120
  }, 'task pane visible at its docked size')
}
async function capture(w, name) {
  // Windows can pause animation frames in an occluded, Outlook-owned task pane.
  await Promise.race([
    evalIn(w, 'new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'),
    wait(350),
  ])
  await wait(180)
  fs.writeFileSync(path.join(home, name + '.png'), (await w.webContents.capturePage()).toPNG())
}
function find(win, mode, pattern) {
  return evalIn(
    win,
    `document.querySelector('#mode').value=${JSON.stringify(
      mode
    )};document.querySelector('#pattern').value=${JSON.stringify(
      pattern
    )};document.querySelector('#query').requestSubmit()`
  )
}
const audit = () =>
  execFileSync(
    'powershell.exe',
    ['-NoProfile', '-File', path.join(root, 'tests/listeners.ps1'), String(process.pid)],
    { windowsHide: true, encoding: 'utf8' }
  )
async function verifyStdio(win) {
  const server = await evalIn(
    win,
    "window.electronAPI.invoke('getSettings').then(v=>v.mcp.servers.find(s=>s.id==='mailpilot').transport)"
  )
  assert.equal(server.type, 'stdio')
  const child = spawn(server.command, server.args, {
    windowsHide: true,
    env: { ...process.env, ...server.env },
    stdio: ['pipe', 'pipe', 'ignore'],
  })
  const lines = createInterface({ input: child.stdout })[Symbol.asyncIterator]()
  let id = 0
  async function call(method, params) {
    child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }) + '\n')
    const next = await lines.next()
    assert(!next.done)
    const reply = JSON.parse(next.value)
    assert.equal(reply.id, id)
    assert(!reply.error)
    return reply.result
  }
  try {
    await call('initialize', { protocolVersion: '2025-06-18' })
    assert.equal((await call('tools/list', {})).tools.length, 4)
    const found = await call('tools/call', {
      name: 'search_mail',
      arguments: { pattern: 'review@example', mode: 'full' },
    })
    const hits = JSON.parse(found.content[0].text).items
    assert.equal(hits.length, 3)
    const read = await call('tools/call', { name: 'read_mail', arguments: { id: hits[0].id, field: 'cc' } })
    assert(JSON.parse(read.content[0].text).text.includes('review@example.org'))
    assert.match(audit(), /PASS/)
  } finally {
    child.stdin.end()
  }
}
async function desktop() {
  app.on('web-contents-created', (_e, contents) => {
    contents.on('console-message', (event, level, message) => {
      if (event.level === 'warning' || event.level === 'error' || level >= 2)
        fs.appendFileSync(path.join(home, 'renderer.log'), (event.message || message) + '\n')
    })
  })
  const childProcess = require('node:child_process'),
    spawnOriginal = childProcess.spawn
  childProcess.spawn = (exe, args, options) => {
    if (args?.at(-1) === '--ui' && path.basename(args[1]) === 'service.py')
      args = ['-B', path.join(root, 'tests/desktop-worker.py')]
    return spawnOriginal(exe, args, options)
  }
  const execOriginal = childProcess.execFile
  if (process.env.MAILPILOT_EXPECT_PANE) {
    childProcess.execFile = (exe, args, opts, cb) =>
      execOriginal(exe, args, opts, (err, out, stderr) => {
        if (args.some((arg) => typeof arg === 'string' && arg.endsWith('pane.py')))
          paneStep([args[2], err ? err.code : 'OK', stderr].join(' '))
        cb(err, out, stderr)
      })
  }
  require(path.join(bundle, 'Desktop/main.cjs'))
  childProcess.spawn = spawnOriginal
  childProcess.execFile = execOriginal
  const search = await page('search')
  await see(search, "document.querySelector('#status').textContent.includes('3 封')")
  assert.equal(
    await evalIn(search, "getComputedStyle(document.querySelector('#mode')).appearance"),
    'base-select'
  )
  await search.webContents.executeJavaScript("document.querySelector('#mode').showPicker()", true)
  await see(search, "document.querySelector('#mode').matches(':open')")
  search.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'Escape' })
  search.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'Escape' })
  await see(search, "!document.querySelector('#mode').matches(':open')")
  const before = await evalIn(search, "document.querySelector('.workspace').offsetWidth")
  await evalIn(
    search,
    "document.querySelector('#splitter').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'}))"
  )
  assert((await evalIn(search, "document.querySelector('.workspace').offsetWidth")) > before)
  await evalIn(search, "document.querySelector('#splitter').dispatchEvent(new MouseEvent('dblclick'))")
  await find(search, 'sender', 'wanning@example')
  await see(search, "document.querySelector('.snippet mark')?.textContent==='wanning@example'")
  await find(search, 'full', 'PO-\\d{6}')
  await see(search, "document.querySelectorAll('.result-row').length===3")
  await capture(search, 'search')
  await evalIn(search, "document.querySelector('.result-row').click()")
  const reader = search
  assert.equal(windows().length, 1)
  assert(
    await evalIn(
      search,
      "document.querySelector('#reading-pane').getBoundingClientRect().left>=document.querySelector('.workspace').getBoundingClientRect().right-1"
    )
  )
  await see(
    reader,
    "document.querySelector('iframe')?.contentDocument?.querySelector('table') && document.querySelector('iframe').contentDocument.querySelectorAll('mark').length===2"
  )
  assert.equal(
    await evalIn(
      reader,
      "document.querySelector('iframe').contentDocument.querySelector('img').getAttribute('src').startsWith('data:image/png')"
    ),
    true
  )
  assert.equal(
    await evalIn(
      reader,
      "document.querySelector('iframe').contentDocument.querySelector('th').getBoundingClientRect().width>55"
    ),
    true
  )
  await capture(reader, 'reader')
  await verifyAttachments(search)
  for (const [sort, first] of [
    ['date-asc', '请核对'],
    ['sender-asc', '请核对'],
    ['subject-desc', '十一月'],
    ['date-desc', '十一月'],
  ]) {
    await evalIn(
      search,
      `document.querySelector('#sort').value='${sort}';document.querySelector('#sort').dispatchEvent(new Event('change'))`
    )
    await see(search, `document.querySelector('.result-row .subject')?.textContent.startsWith('${first}')`)
  }
  await find(search, 'full', '(?<=📨)audit-only')
  await see(search, "document.querySelector('.snippet mark')?.textContent==='audit-only'")
  await evalIn(search, "document.querySelector('.result-row').click()")
  await see(reader, "document.querySelector('details[open] mark')?.textContent==='audit-only'")
  await find(search, 'full', '尾码-9823')
  await see(search, "document.querySelector('.snippet mark')?.textContent==='尾码-9823'")
  await evalIn(search, "document.querySelector('.result-row').click()")
  await see(
    reader,
    "document.querySelector('iframe')?.contentDocument?.querySelector('mark.current')?.textContent==='尾码-9823'"
  )
  await evalIn(search, "document.querySelector('[aria-label=设置]').click()")
  const settings = await page('settings')
  await see(settings, "document.querySelector('[data-palette=ocean]')")
  await capture(settings, 'settings')
  await evalIn(
    settings,
    "document.querySelector('[data-choice=dark]').click();document.querySelector('[data-palette=ocean]').click();document.querySelector('#save').click()"
  )
  await see(reader, "document.documentElement.dataset.theme==='dark'")
  assert.equal(JSON.parse(fs.readFileSync(path.join(home, 'settings.json'))).palette, 'ocean')
  await evalIn(settings, "document.querySelector('[data-section=windows]').click()")
  const changeReader = async (value) => {
    await evalIn(
      settings,
      `let sel=document.querySelector('#readerLayout');sel.value='${value}';sel.dispatchEvent(new Event('change'));document.querySelector('#save').click()`.replace(
        'let sel=',
        'var sel='
      )
    )
    await see(search, `document.querySelector('#reading-pane').hidden===${value === 'window'}`)
  }
  await changeReader('window')
  await evalIn(search, "document.querySelector('.result-row').click()")
  const separate = await page('reader')
  await see(separate, "document.querySelector('#letter .attachment-open')")
  await evalIn(separate, "document.querySelector('[aria-label=关闭]').click()")
  await changeReader('pane')
  await see(search, "document.querySelector('#letter .attachment-open')")
  paneStep('Docking search')
  await evalIn(search, "document.querySelector('.dock-button').click()")
  await see(
    search,
    "['edge','outlook'].includes(document.body.dataset.layout) && document.querySelector('#reading-pane').hidden"
  )
  if (process.env.MAILPILOT_EXPECT_PANE) {
    assert.equal(await evalIn(search, 'document.body.dataset.layout'), 'outlook')
    paneStep('Waiting for the visible task pane to take its docked size')
    await checkPaneBounds(search)
    paneStep('Native sidebar bounds ' + JSON.stringify(search.getBounds()))
  }
  paneStep('Opening a search result from the sidebar')
  await evalIn(search, "document.querySelector('.result-row').click()")
  const sidebarReader = await page('reader')
  await see(sidebarReader, "document.querySelector('#letter .attachment-open')")
  await evalIn(sidebarReader, "document.querySelector('[aria-label=关闭]').click()")
  paneStep('Capturing the sidebar')
  await capture(search, 'sidebar')
  paneStep('Restoring the floating search')
  await evalIn(search, "document.querySelector('.dock-button').click()")
  await see(
    search,
    "document.body.dataset.layout==='window' && !document.querySelector('#reading-pane').hidden"
  )
  paneStep('Search floated')
  await evalIn(settings, "document.querySelector('[data-section=mailbox]').click()")
  const newDir = path.join(home, '自定义 索引')
  await evalIn(
    settings,
    `const dir=document.querySelector('#indexDir');dir.value=${JSON.stringify(
      newDir
    )};dir.dispatchEvent(new Event('input'));document.querySelector('#save').click()`
  )
  await see(search, "document.querySelector('#status').textContent.includes('0 封')")
  await evalIn(settings, "document.querySelector('[aria-label=关闭]').click()")
  await evalIn(search, "document.querySelector('[aria-label=设置]').click()")
  const reopened = await page('settings')
  await see(reopened, "document.querySelector('[data-section=mailbox]')")
  await evalIn(reopened, "document.querySelector('[data-section=mailbox]').click()")
  assert.equal(await evalIn(reopened, "document.querySelector('#indexDir').value"), newDir)
  assert.equal(await evalIn(search, "document.querySelector('#reading-pane').dataset.state"), 'empty')
  assert.equal(await evalIn(search, "document.querySelector('#pattern').value"), '尾码-9823')
  assert.match(audit(), /PASS/)
}
async function verifyAttachments(win) {
  const downloads = path.join(home, 'downloads')
  fs.mkdirSync(downloads)
  const q = (s) => 'document.querySelector(' + JSON.stringify(s) + ')'
  const click = (s) => evalIn(win, q(s) + '.click()')
  const names = await evalIn(
    win,
    "[...document.querySelectorAll('.attachment-info b')].map(n=>n.textContent)"
  )
  assert(names.length >= 8)
  const first = names[0],
    original = (n) => fs.readFileSync(path.join(home, 'originals', n))
  const one = path.join(downloads, first)
  dialog.showSaveDialog = async () => ({ canceled: true })
  const options = '.attachment .icon-btn'
  await click(options)
  await see(win, "document.querySelector('.file-menu').matches(':popover-open')")
  const command = (label) => '.file-menu [aria-label="' + label + '"]'
  await click(command('下载'))
  assert(!fs.existsSync(one))
  dialog.showSaveDialog = async () => ({ filePath: one })
  dialog.showOpenDialog = async () => ({ filePaths: [downloads] })
  await evalIn(
    win,
    q('.attachment').concat(".dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}))")
  )
  await click(command('下载'))
  await until(() => fs.existsSync(one), 'single attachment saved')
  assert.deepEqual(fs.readFileSync(one), original(first))
  await click(options)
  await click(command('复制'))
  const clipboard = path.join(home, 'clipboard.json')
  const copied = () => JSON.parse(fs.readFileSync(clipboard))
  await until(() => fs.existsSync(clipboard) && copied().length === 1, 'single CF_HDROP file')
  await click('[aria-label=下载全部]')
  await until(
    () => fs.readdirSync(downloads).filter((n) => !n.startsWith('.')).length === names.length + 1,
    'all attachments saved'
  )
  assert.deepEqual(
    fs.readFileSync(path.join(downloads, path.parse(first).name + ' (2).xlsx')),
    original(first)
  )
  for (const n of names) assert.deepEqual(fs.readFileSync(path.join(downloads, n)), original(n))
  await click('[aria-label=复制全部]')
  await until(() => copied().length === names.length, 'all clipboard files')
  for (const p of copied()) assert.deepEqual(fs.readFileSync(p), original(path.basename(p)))
  const times = []
  await evalIn(win, "document.querySelector('.extra-attachments')?.setAttribute('open','')")
  for (const name of [names[0], names[1], ...names.slice(1)]) {
    const start = performance.now()
    await click('[aria-label="预览 ' + name + '"]')
    const frame = await until(
      () => win.webContents.mainFrame.frames.find((f) => f.url.endsWith('/viewer.html')),
      'attachment preview frame'
    )
    const inside = (code) => frame.executeJavaScript(code)
    const ext = name === '收货照片' ? 'jpeg' : path.extname(name).slice(1)
    await until(async () => {
      const state = await inside("document.querySelector('#surface').dataset.state")
      if (state === 'error') throw Error(await inside("document.querySelector('#viewer-state').title"))
      return state === 'ready' && (await inside("document.querySelector('#surface').dataset.format")) === ext
    }, 'render ' + name)
    times.push({ format: ext, ms: Math.round(performance.now() - start) })
    fs.writeFileSync(path.join(home, 'preview-times.json'), JSON.stringify(times))
    if (ext === 'pdf' || ext === 'pptx') {
      await inside("document.querySelector('#next-page').click()")
      await until(
        () => inside("document.querySelector('#page-label').textContent.includes('2 / 2')"),
        'second page'
      )
    }
    if (ext === 'md') {
      assert.equal(await inside("document.querySelector('.document-text h1')?.textContent"), '采购记录')
      assert.equal(await inside("document.querySelector('.document-text table td')?.textContent"), '纸张')
    }
    if (ext === 'txt') assert.match(await inside("document.querySelector('pre').textContent"), /周三/)
    if (['png', 'jpeg', 'webp'].includes(ext)) {
      assert.equal(await inside("document.querySelector('img').naturalWidth"), ext === 'png' ? 80 : 12)
      await inside("document.querySelector('#plus').click()")
      assert.match(await inside("document.querySelector('#page-label').textContent"), /125%/)
    }
    if (ext === 'xlsx') {
      assert.match(await inside("document.querySelector('#surface').innerText"), /采购清单/)
      await capture(win, 'spreadsheet-preview')
      await inside(
        "[...document.querySelectorAll('#surface *')].find(n=>n.childElementCount===0&&n.textContent==='复核').click()"
      )
      await until(
        () => inside("document.querySelector('#page-label').textContent.includes('2 / 2')"),
        'second sheet'
      )
    }
    if (ext === 'doc') assert.match(await inside("document.querySelector('#surface').innerText"), /交付说明/)
    await click('[aria-label=返回邮件]')
    await see(win, "!document.querySelector('.preview-dialog').open")
  }
  await click('[aria-label="预览 ' + names[0] + '"]')
  await click('[aria-label=下一个附件]')
  await click('[aria-label=下一个附件]')
  const frame = await until(
    () => win.webContents.mainFrame.frames.find((f) => f.url.endsWith('/viewer.html')),
    'quick switch'
  )
  await until(
    () =>
      frame.executeJavaScript(
        "document.querySelector('#surface').matches('[data-state=ready][data-format=docx]')"
      ),
    'latest attachment wins'
  )
  await frame.executeJavaScript("window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
  await see(
    win,
    "!document.querySelector('.preview-dialog').open && document.querySelector('.result-row.selected')"
  )
  fs.writeFileSync(path.join(home, 'preview-times.json'), JSON.stringify(times))
}
async function assistant() {
  // Same bootstrap, compiled renderer, preload and stdio MCP transport as the distributed app.
  require(path.join(bundle, 'Chatbox/bootstrap.cjs'))
  const win = await until(
    () => windows().find((w) => w.webContents.getURL().includes('/renderer/index.html')),
    'Chatbox'
  )
  await see(win, "typeof window.electronAPI?.onMailPilotLayout==='function'")
  await see(
    win,
    "document.querySelector('textarea') || document.querySelector('[contenteditable=true]') || document.querySelector('.controls')"
  )
  await wait(1400)
  await verifyStdio(win)
  const readTheme = () => evalIn(win, 'document.documentElement.dataset.theme')
  const profile = path.join(home, 'settings.json'),
    cfg = JSON.parse(fs.readFileSync(profile))
  fs.writeFileSync(profile, JSON.stringify({ ...cfg, theme: 'dark', palette: 'ocean' }))
  await until(async () => (await readTheme()) === 'dark', 'Chatbox theme updated in place')
  assert.match(audit(), /PASS/)
  const state = () => evalIn(win, "window.electronAPI.invoke('mailpilot:panel','state')")
  await evalIn(win, "window.electronAPI.invoke('mailpilot:panel','toggle')")
  await until(async () => ['edge', 'outlook'].includes(await state()), 'AI docked')
  if (process.env.MAILPILOT_EXPECT_PANE) {
    assert.equal(await state(), 'outlook')
    await checkPaneBounds(win)
  }
  await evalIn(win, "window.electronAPI.invoke('mailpilot:panel','toggle')")
  await until(async () => (await state()) === 'window', 'AI floated')
  assert.match(audit(), /PASS/)
}
;(process.env.MAILPILOT_TEST_AI === '1' ? assistant() : desktop())
  .then(() => {
    fs.writeFileSync(path.join(home, 'result.txt'), 'PASS')
    app.exit(0)
  })
  .catch((e) => {
    fs.writeFileSync(path.join(home, 'result.txt'), e.stack)
    app.exit(1)
  })
