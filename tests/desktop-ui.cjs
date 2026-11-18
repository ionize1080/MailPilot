'use strict'
const assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path')
const { app, BrowserWindow } = require('electron')
const { execFileSync, spawn } = require('node:child_process')
const { createInterface } = require('node:readline')
const root = path.resolve(__dirname, '..'),
  bundle = process.env.MAILPILOT_QA_BUNDLE || path.join(root, 'dist/MailPilot'),
  home = process.env.MAILPILOT_HOME
assert(path.resolve(home).startsWith(path.join(root, '.build') + path.sep))
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const evalIn = (win, code) => win.webContents.executeJavaScript(code)
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
async function capture(w, name) {
  await evalIn(w, 'new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
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
  require(path.join(bundle, 'Desktop/main.cjs'))
  const search = await page('search')
  await see(search, "document.querySelector('#status').textContent.includes('3 封')")
  await find(search, 'sender', 'wanning@example')
  await see(search, "document.querySelector('.snippet mark')?.textContent==='wanning@example'")
  await find(search, 'full', 'PO-\\d{6}')
  await see(search, "document.querySelectorAll('.result-row').length===3")
  await capture(search, 'search')
  await evalIn(search, "document.querySelector('.result-row').click()")
  const reader = await page('reader')
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
  await evalIn(search, "document.querySelector('.dock-button').click()")
  await see(search, "['edge','outlook'].includes(document.body.dataset.layout)")
  if (process.env.MAILPILOT_EXPECT_PANE)
    assert.equal(await evalIn(search, 'document.body.dataset.layout'), 'outlook')
  await capture(search, 'sidebar')
  await evalIn(search, "document.querySelector('.dock-button').click()")
  await see(search, "document.body.dataset.layout==='window'")
  assert.equal(await evalIn(search, "document.querySelector('#pattern').value"), '尾码-9823')
  assert.match(audit(), /PASS/)
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
  if (process.env.MAILPILOT_EXPECT_PANE) assert.equal(await state(), 'outlook')
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
