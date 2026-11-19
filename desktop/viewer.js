const $ = (id) => document.getElementById(id)
const officeDir = './node_modules/@silurus/ooxml/dist/'
const legacyDir = './node_modules/@silurus/ooxml-legacy-office/dist/'
const pdfDir = './node_modules/pdfjs-dist/'
let active
function pageInfo(index, total, unit = '页') {
  $('page-label').textContent = `第 ${index + 1} / ${total} ${unit}`
  $('prev-page').disabled = !index
  $('next-page').disabled = index + 1 >= total
}
function actions(model) {
  const view = active
  for (const [id, fn] of Object.entries(model)) {
    $(id).hidden = !fn
    $(id).onclick = fn
      ? () =>
          Promise.resolve()
            .then(fn)
            .catch((e) => showError(view, e))
      : null
  }
}
function showError(view, error) {
  if (!view || active !== view || view.signal.aborted) return
  const msg =
    error.code === 'unsupported-content'
      ? '这份旧版文档含有预览器暂不支持的内容。'
      : error.name === 'PasswordException'
      ? '这份文档受密码保护。'
      : '无法预览这份文件。'
  $('viewer-state').textContent = msg + '可下载后用原应用打开。'
  $('viewer-state').title = error.message
  $('viewer-state').hidden = false
  $('surface').dataset.state = 'error'
  console.warn('Preview:', error.message)
}
function mount(tag, cls) {
  const node = document.createElement(tag)
  node.className = cls
  $('surface').replaceChildren(node)
  return node
}
async function bytes(v, range) {
  const response = await fetch(v.url, { signal: v.signal, headers: range ? { Range: range } : {} })
  if (!response.ok) throw Error('无法读取文件')
  return response
}
async function office(v) {
  const isSheet = v.kind === 'sheet',
    isWord = v.kind === 'word',
    fmt = isSheet ? 'xlsx' : isWord ? 'docx' : 'pptx'
  const legacy = ['doc', 'xls', 'ppt'].includes(v.ext)
  const [lib, addOn, data] = await Promise.all([
    import(officeDir + fmt + '.mjs'),
    legacy ? import(legacyDir + v.ext + '.mjs') : {},
    bytes(v).then((r) => r.arrayBuffer()),
  ])
  v.signal.throwIfAborted()
  const box = mount('div', isSheet ? 'sheet-mount' : 'canvas-mount')
  const canvas = document.createElement('canvas')
  if (!isSheet) box.append(canvas)
  const page = (i, n) => {
    if (v === active && n) pageInfo(i, n, isSheet ? '张工作表' : isWord ? '页' : '张幻灯片')
  }
  const opts = {
    mode: 'worker',
    fonts: [],
    progressiveLayout: true,
    enableHyperlinks: false,
    enableMediaPlayback: false,
    showZoomSlider: false,
    enableTextSelection: true,
    width: Math.max(260, $('surface').clientWidth - 36),
    onPageChange: page,
    onSlideChange: page,
    onSheetChange: page,
    onError: (e) => showError(v, e),
  }
  if (legacy) {
    const key = isWord ? 'legacyDoc' : isSheet ? 'legacyXls' : 'legacyPpt'
    // The legacy reader accepts blob URLs for locally bundled parser assets.
    const urls = await Promise.all(
      ['legacy-' + v.ext + '-source-module.mjs', 'legacy_' + v.ext + '_direct_bg.wasm'].map(async (name) => {
        const response = await fetch(legacyDir + name, { signal: v.signal })
        if (!response.ok) throw Error('缺少文档预览组件')
        const blob = await response.blob()
        v.signal.throwIfAborted()
        const url = URL.createObjectURL(blob)
        v.signal.addEventListener('abort', () => URL.revokeObjectURL(url), { once: true })
        return url
      })
    )
    const factory = isWord ? addOn.createLegacyDoc : isSheet ? addOn.createLegacyXls : addOn.createLegacyPpt
    opts[key] = factory({ moduleUrl: urls[0], wasmUrl: urls[1] })
  }
  const delimited = ['csv', 'tsv'].includes(v.ext)
  if (delimited) box.append(canvas)
  const viewer = delimited
    ? new lib.XlsxSheetViewer(canvas, opts)
    : isSheet
    ? new lib.XlsxViewer(box, opts)
    : isWord
    ? new lib.DocxViewer(canvas, opts)
    : new lib.PptxViewer(canvas, opts)
  v.cleanup = () => viewer.destroy()
  try {
    await viewer.load(data, delimited ? { format: v.ext, sheetName: '数据' } : undefined)
  } catch (e) {
    if (!legacy || e.code !== 'unsupported-content') throw e
    v.signal.throwIfAborted()
    viewer.destroy()
    v.cleanup = null
    await legacyContent(v)
    return
  }
  v.signal.throwIfAborted()
  const previous = () => (isWord ? viewer.prevPage() : isSheet ? viewer.prevSheet() : viewer.prevSlide())
  const next = () => (isWord ? viewer.nextPage() : isSheet ? viewer.nextSheet() : viewer.nextSlide())
  actions({
    'prev-page': isSheet ? null : previous,
    'next-page': isSheet ? null : next,
    less: () => viewer.zoomOut(),
    plus: () => viewer.zoomIn(),
    fit: () => (isSheet ? viewer.setScale(1) : viewer.fitPage()),
  })
  if (isSheet) page(viewer.sheetIndex, viewer.sheetCount)
  else page(isWord ? viewer.currentPage : viewer.slideIndex, isWord ? viewer.pageCount : viewer.slideCount)
}
async function legacyContent(v) {
  const parser = new Worker('./legacy-preview.mjs', { type: 'module' })
  v.cleanup = () => parser.terminate()
  const [data] = await Promise.all([
    bytes(v).then((r) => r.arrayBuffer()),
    import('./node_modules/dompurify/dist/purify.min.js'),
  ])
  v.signal.throwIfAborted()
  const contents = await new Promise((resolve, reject) => {
    parser.onmessage = (e) => (e.data.error ? reject(Error(e.data.error)) : resolve(e.data))
    parser.onerror = (e) => reject(Error(e.message))
    v.signal.addEventListener('abort', () => reject(v.signal.reason), { once: true })
    parser.postMessage({ format: v.ext, bytes: data }, [data])
  })
  parser.terminate()
  v.signal.throwIfAborted()
  $('surface').dataset.kind = 'text'
  const node = mount(contents.text ? 'pre' : 'article', 'document-text')
  if (contents.text) node.textContent = contents.text
  else node.innerHTML = cleanDocument(contents.html)
  textControls(node, contents.partial ? '内容预览 · 已截取前 512 K 字符' : '内容预览')
}
function cleanDocument(html) {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'h6',
      'p',
      'ul',
      'ol',
      'li',
      'b',
      'strong',
      'em',
      'i',
      'del',
      'pre',
      'code',
      'blockquote',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
      'hr',
      'br',
      'a',
    ],
    ALLOWED_ATTR: [],
  })
}
async function pdf(v) {
  const lib = await import(pdfDir + 'build/pdf.min.mjs')
  v.signal.throwIfAborted()
  lib.GlobalWorkerOptions.workerSrc = new URL(pdfDir + 'build/pdf.worker.min.mjs', location.href).href
  const task = lib.getDocument({
    url: v.url,
    cMapUrl: pdfDir + 'cmaps/',
    cMapPacked: true,
    standardFontDataUrl: pdfDir + 'standard_fonts/',
    wasmUrl: pdfDir + 'wasm/',
    iccUrl: pdfDir + 'iccs/',
    isEvalSupported: false,
    enableXfa: false,
    useSystemFonts: true,
  })
  v.cleanup = () => task.destroy().catch(() => {})
  const doc = await task.promise
  v.signal.throwIfAborted()
  const holder = mount('div', 'canvas-mount')
  let number = 1,
    zoom = 1,
    revision = 0,
    rendering
  async function draw() {
    const turn = ++revision
    rendering?.cancel()
    const page = await doc.getPage(number)
    if (turn !== revision || v !== active) return
    const natural = page.getViewport({ scale: 1 })
    const area = $('surface')
    const scale =
      Math.min((area.clientWidth - 32) / natural.width, (area.clientHeight - 32) / natural.height) * zoom
    const viewport = page.getViewport({ scale: Math.max(0.05, scale) })
    const dpr = Math.min(devicePixelRatio, 2, Math.sqrt(8000000 / (viewport.width * viewport.height)))
    const canvas = document.createElement('canvas')
    canvas.width = Math.ceil(viewport.width * dpr)
    canvas.height = Math.ceil(viewport.height * dpr)
    canvas.style.width = viewport.width + 'px'
    canvas.style.height = viewport.height + 'px'
    rendering = page.render({ canvas, viewport, transform: [dpr, 0, 0, dpr, 0, 0] })
    try {
      await rendering.promise
    } catch (e) {
      if (e.name !== 'RenderingCancelledException') throw e
      return
    }
    if (turn !== revision || v !== active) return
    holder.replaceChildren(canvas)
    pageInfo(number - 1, doc.numPages)
  }
  actions({
    'prev-page': () => {
      number = Math.max(1, number - 1)
      return draw()
    },
    'next-page': () => {
      number = Math.min(doc.numPages, number + 1)
      return draw()
    },
    less: () => {
      zoom = Math.max(0.5, zoom / 1.25)
      return draw()
    },
    plus: () => {
      zoom = Math.min(4, zoom * 1.25)
      return draw()
    },
    fit: () => {
      zoom = 1
      return draw()
    },
  })
  await draw()
  v.resize = draw
}
async function raster(v) {
  const mime = { jpg: 'jpeg', ico: 'x-icon' }[v.ext] || v.ext
  const blob = await (await bytes(v)).blob()
  v.signal.throwIfAborted()
  const url = URL.createObjectURL(blob.slice(0, blob.size, 'image/' + mime))
  v.cleanup = () => URL.revokeObjectURL(url)
  const image = mount('img', 'image-preview')
  image.alt = '图片附件'
  image.src = url
  await image.decode()
  v.signal.throwIfAborted()
  let zoom = 1
  function size() {
    const area = $('surface')
    const factor = Math.min(
      1,
      (area.clientWidth - 32) / image.naturalWidth,
      (area.clientHeight - 32) / image.naturalHeight
    )
    image.style.width = Math.max(1, Math.round(image.naturalWidth * factor * zoom)) + 'px'
    $('page-label').textContent = `${image.naturalWidth} × ${image.naturalHeight} · ${Math.round(
      factor * zoom * 100
    )}%`
  }
  actions({
    'prev-page': null,
    'next-page': null,
    less: () => {
      zoom = Math.max(0.25, zoom / 1.25)
      size()
    },
    plus: () => {
      zoom = Math.min(8, zoom * 1.25)
      size()
    },
    fit: () => {
      zoom = 1
      size()
    },
  })
  image.ondblclick = () => {
    zoom = zoom === 1 ? image.naturalWidth / image.width : 1
    size()
  }
  v.resize = size
  size()
}
async function textPreview(v) {
  const limit = 512 * 1024
  const response = await bytes(v, v.size === 0 ? undefined : 'bytes=0-' + (limit - 1))
  const buf = new Uint8Array(await response.arrayBuffer())
  v.signal.throwIfAborted()
  let text
  if (buf[0] === 255 && buf[1] === 254) text = new TextDecoder('utf-16le').decode(buf)
  else if (buf[0] === 254 && buf[1] === 255) text = new TextDecoder('utf-16be').decode(buf)
  else {
    try {
      text = new TextDecoder('utf-8', { fatal: true }).decode(buf, { stream: buf.length === limit })
    } catch {
      text = new TextDecoder('gb18030').decode(buf)
    }
  }
  const markdown = v.kind === 'markdown'
  const node = mount(markdown ? 'article' : 'pre', 'document-text')
  if (markdown) {
    const [{ marked }] = await Promise.all([
      import('./node_modules/marked/lib/marked.esm.js'),
      import('./node_modules/dompurify/dist/purify.min.js'),
    ])
    v.signal.throwIfAborted()
    node.innerHTML = cleanDocument(marked.parse(text))
  } else node.textContent = text
  const total = Number(response.headers.get('Content-Range')?.split('/')[1] || buf.length)
  textControls(node, total > buf.length ? '预览前 512 KiB' : markdown ? 'Markdown' : '纯文本')
}
function textControls(node, label) {
  $('page-label').textContent = label
  let scale = 1
  const font = (delta) => {
    scale = delta ? Math.max(0.7, Math.min(2, scale + delta)) : 1
    node.style.fontSize = scale + 'rem'
  }
  actions({
    'prev-page': null,
    'next-page': null,
    less: () => font(-0.1),
    plus: () => font(0.1),
    fit: () => font(0),
  })
}
function clear() {
  active?.abort.abort()
  active?.cleanup?.()
  active = null
  clearTimeout(resizeTimer)
  $('surface').replaceChildren()
  $('surface').dataset.state = 'empty'
  $('viewer-bar').hidden = true
  for (const b of $('viewer-bar').querySelectorAll('button')) b.onclick = null
}
async function open(data) {
  clear()
  const abort = new AbortController()
  const v = (active = { ...data, abort, signal: abort.signal })
  document.documentElement.dataset.theme = v.theme
  $('surface').replaceChildren()
  $('surface').dataset.kind = v.kind
  $('surface').dataset.format = v.ext
  $('surface').dataset.state = 'loading'
  $('viewer-state').hidden = false
  $('viewer-state').textContent = '正在渲染…'
  $('viewer-bar').hidden = true
  try {
    if (v.kind === 'image') await raster(v)
    else if (v.kind === 'pdf') await pdf(v)
    else if (['word', 'sheet', 'slides'].includes(v.kind)) await office(v)
    else await textPreview(v)
    if (v !== active) return
    $('viewer-state').hidden = true
    $('viewer-bar').hidden = false
    $('surface').dataset.state = 'ready'
  } catch (e) {
    showError(v, e)
  }
}
let resizeTimer
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (active?.resize) Promise.resolve(active.resize()).catch((e) => showError(active, e))
  }, 90)
})
window.addEventListener('message', (e) => {
  if (e.source !== parent) return
  if (e.data?.type === 'clear') clear()
  if (e.data?.type === 'open' && e.data.url?.startsWith(location.origin + '/file/')) open(e.data)
})
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') parent.postMessage({ type: 'close' }, '*')
  if (e.altKey && ['ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault()
    parent.postMessage({ type: 'step', delta: e.key === 'ArrowRight' ? 1 : -1 }, '*')
  }
})
parent.postMessage({ type: 'ready' }, '*')
