'use strict'
const { app, dialog, protocol } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { Readable } = require('node:stream')
const { randomUUID } = require('node:crypto')

const origin = 'mailpilot-preview://local'
const frameURL = origin + '/viewer.html'
const limit = 96 * 1024 * 1024
const blobs = new Map()
let temp
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'mailpilot-preview',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
      codeCache: true,
    },
  },
])

const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.wasm': 'application/wasm',
  '.ttf': 'font/ttf',
  '.woff2': 'font/woff2',
}
async function serve(request) {
  const url = new URL(request.url)
  const parts = url.pathname.slice(1).split('/').map(decodeURIComponent)
  if (url.host !== 'local' || parts.some((p) => !p || p === '.' || p === '..' || /[\\/:\x00]/.test(p)))
    return new Response(null, { status: 404 })
  const file = blobs.get(parts[1])
  const raw = parts[0] === 'file' && parts.length === 2
  const asset = parts.join('/')
  if (
    raw
      ? !file
      : !/^(viewer\.(?:html|js|css)|legacy-preview\.mjs|ui\.css|node_modules\/(?:@silurus\/(?:ooxml|ooxml-legacy-office)\/dist|office-oxide-wasm\/web|pdfjs-dist\/(?:build|wasm|iccs|cmaps|standard_fonts)|dompurify\/dist|marked\/lib)\/[^:]+)$/.test(
          asset
        )
  )
    return new Response(null, { status: 404 })
  const local = raw ? file.path : path.join(__dirname, ...parts)
  try {
    const { size } = await fs.promises.stat(local)
    let start = 0,
      end = size - 1,
      status = 200
    const headers = {
      'Content-Type': raw
        ? 'application/octet-stream'
        : types[path.extname(local)] || 'application/octet-stream',
      'X-Content-Type-Options': 'nosniff',
      'Accept-Ranges': 'bytes',
    }
    if (raw) headers['Content-Security-Policy'] = "default-src 'none'"
    const range = request.headers.get('range')
    if (raw && range) {
      const bounds = /^bytes=(\d+)-(\d*)$/.exec(range)
      if (!bounds || +bounds[1] >= size || (bounds[2] && +bounds[2] < +bounds[1]))
        return new Response(null, { status: 416, headers: { 'Content-Range': 'bytes */' + size } })
      start = +bounds[1]
      if (bounds[2]) end = Math.min(end, +bounds[2])
      headers['Content-Range'] = `bytes ${start}-${end}/${size}`
      status = 206
    }
    headers['Content-Length'] = String(end - start + 1)
    return new Response(size ? Readable.toWeb(fs.createReadStream(local, { start, end })) : null, {
      headers,
      status,
    })
  } catch {
    return new Response(null, { status: 404 })
  }
}
function install() {
  protocol.handle('mailpilot-preview', serve)
  app.on('will-quit', () => {
    if (temp) fs.rmSync(temp, { recursive: true, force: true, maxRetries: 2 })
  })
}
function discard(file) {
  blobs.delete(file.token)
  fs.promises.unlink(file.path).catch(() => {})
}
function reset(v) {
  v.previewAbort?.abort()
  v.previewTicket = (v.previewTicket || 0) + 1
  for (const file of v.previews?.values() || []) discard(file)
  v.previews = new Map()
}
async function preview(v, worker, args, file, ticket, signal) {
  if (ticket !== v.previewTicket) throw Error('已切换附件')
  if (file.size > limit) throw Error('此附件超过 96 MiB，可下载后查看。')
  const cache = (v.previews ||= new Map())
  const key = JSON.stringify([v.source, args.key, args.stamp, args.index])
  let item = cache.get(key)
  if (item) cache.delete(key)
  else {
    temp ||= fs.mkdtempSync(path.join(app.getPath('temp'), 'MailPilot-preview-'))
    const token = randomUUID()
    item = { token, path: path.join(temp, token) }
    try {
      await worker.call('attachment_transfer', { ...args, action: 'preview', destination: item.path }, signal)
      item.size = (await fs.promises.stat(item.path)).size
      if (item.size > limit) throw Error('此附件超过 96 MiB，可下载后查看。')
      if (v.previews !== cache || v.win.isDestroyed()) throw Error('阅读窗已关闭')
      blobs.set(token, item)
    } catch (e) {
      discard(item)
      throw e
    }
  }
  cache.set(key, item)
  let bytes = [...cache.values()].reduce((n, entry) => n + entry.size, 0)
  for (const [k, old] of cache) {
    if (cache.size <= 4 && bytes <= 128 * 1024 * 1024) break
    bytes -= old.size
    cache.delete(k)
    discard(old)
  }
  return { url: origin + '/file/' + item.token, size: item.size }
}
async function handle(v, worker, action, request) {
  if (action === 'dismiss') {
    v.previewAbort?.abort()
    v.previewTicket = (v.previewTicket || 0) + 1
    return
  }
  const { id, key, stamp, index } = request
  const args = { id, key, stamp, index }
  if (!['preview', 'save', 'copy'].includes(action)) throw Error('未知附件操作')
  let ticket, signal
  if (action === 'preview') {
    v.previewAbort?.abort()
    v.previewAbort = new AbortController()
    signal = v.previewAbort.signal
    ticket = v.previewTicket = (v.previewTicket || 0) + 1
  }
  const files = await worker.call('attachment_info', args)
  if (index !== null && (!Number.isInteger(index) || !files[index])) throw Error('附件已更改')
  if (action === 'preview') {
    if (index === null) throw Error('请选择一个附件')
    const run = () => preview(v, worker, args, files[index], ticket, signal)
    v.previewQueue = (v.previewQueue || Promise.resolve()).then(run, run)
    return v.previewQueue
  }
  let destination
  if (action === 'save') {
    if (index === null) {
      const result = await dialog.showOpenDialog(v.win, {
        title: '下载全部附件到',
        properties: ['openDirectory', 'createDirectory'],
      })
      if (result.canceled) return null
      destination = result.filePaths[0]
    } else {
      const result = await dialog.showSaveDialog(v.win, {
        title: '附件另存为',
        defaultPath: files[index].name,
      })
      if (result.canceled) return null
      destination = result.filePath
    }
  }
  return worker.call('attachment_transfer', { ...args, action, destination })
}
module.exports = { install, frameURL, reset, handle }
