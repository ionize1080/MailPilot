'use strict'
// Original author styles are only installed inside a scriptless, isolated mail document.
function mailDocument(data, cfg, external) {
  let remote = false
  const images = new Map()
  for (const [key, dataUrl] of Object.entries(data.inlineImages)) images.set(key.toLowerCase(), dataUrl)
  for (const file of data.files) {
    if (file.cid && file.location && images.has(file.cid.toLowerCase()))
      images.set(file.location.toLowerCase(), images.get(file.cid.toLowerCase()))
  }
  DOMPurify.addHook('uponSanitizeAttribute', (_node, attr) => {
    if (!['src', 'background'].includes(attr.attrName)) return
    let value = attr.attrValue.trim()
    try {
      value = decodeURIComponent(value)
    } catch {}
    const inline = images.get(value.replace(/^cid:/i, '').replace(/^<|>$/g, '').toLowerCase())
    if (inline) {
      attr.attrValue = inline
      return
    }
    if (/^https?:\/\//i.test(value)) {
      remote = true
      attr.keepAttr = external
      return
    }
    attr.keepAttr = /^data:image\/(?:png|jpe?g|gif|webp|bmp);base64,/i.test(value)
  })
  let doc
  try {
    const markup = data.html.replace(/<!--\s*\[if\s+!(?:vml|mso)\]\s*>([\s\S]*?)<!\[endif\]\s*-->/gi, '$1')
    doc = DOMPurify.sanitize(markup, {
      WHOLE_DOCUMENT: true,
      RETURN_DOM: true,
      USE_PROFILES: { html: true },
      FORBID_TAGS: [
        'meta',
        'base',
        'link',
        'form',
        'input',
        'button',
        'select',
        'textarea',
        'video',
        'audio',
        'source',
        'template',
      ],
      FORBID_ATTR: ['srcset', 'target', 'download', 'autofocus', 'contenteditable', 'tabindex', 'ping'],
      ALLOW_DATA_ATTR: false,
    })
  } finally {
    DOMPurify.removeHook('uponSanitizeAttribute')
  }
  if (!remote)
    remote = Array.from(doc.querySelectorAll('style,[style]')).some((node) =>
      /url\(\s*["']?https?:\/\//i.test(
        node.tagName === 'STYLE' ? node.textContent : node.getAttribute('style')
      )
    )
  const base = doc.ownerDocument.createElement('style')
  base.textContent =
    'html{color-scheme:light;background:white}body{margin:0;color:#202124;font:11pt Calibri,Arial,sans-serif}a{color:#155aa6}'
  const head = doc.querySelector('head'),
    policy = doc.ownerDocument.createElement('meta')
  policy.httpEquiv = 'Content-Security-Policy'
  policy.content =
    "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:" +
    (external ? ' https: http:' : '') +
    "; base-uri 'none'; form-action 'none'"
  head.prepend(policy, base)
  const appearance = doc.ownerDocument.createElement('style')
  appearance.textContent =
    'html{zoom:' +
    cfg.readerZoom +
    '%}mark.mailpilot-hit{background:' +
    cfg.highlightColor +
    '!important;color:' +
    contrastInk(cfg.highlightColor) +
    '!important;border-radius:2px}mark.mailpilot-hit.current{outline:2px solid #b36912!important}mark.mailpilot-hit:empty{border-left:2px solid #b36912}'
  head.append(appearance)
  return { html: '<!doctype html>' + doc.outerHTML, remote }
}

function visibleMailText(doc) {
  const nodes = [],
    pieces = []
  let length = 0
  const append = (s) => {
    pieces.push(s)
    length += s.length
  }
  const line = () => {
    if (length && !pieces.at(-1).endsWith('\n')) append('\n')
  }
  const blocks = new Set('P DIV LI TR H1 H2 H3 H4 H5 H6 BLOCKQUOTE PRE SECTION ARTICLE HR TABLE'.split(' '))
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.data) {
        nodes.push({ node, start: length, end: length + node.length })
        append(node.data)
      }
      return
    }
    if (node.nodeType !== Node.ELEMENT_NODE || ['STYLE', 'SCRIPT', 'TEMPLATE', 'HEAD'].includes(node.tagName))
      return
    const css = doc.defaultView.getComputedStyle(node)
    if (css.display === 'none' || css.visibility === 'hidden') return
    if (node.tagName === 'BR') {
      append('\n')
      return
    }
    if (blocks.has(node.tagName)) line()
    for (const child of node.childNodes) walk(child)
    if (blocks.has(node.tagName)) line()
    if (node.tagName === 'TD' || node.tagName === 'TH') append('\t')
  }
  walk(doc.body)
  return { text: pieces.join(''), nodes }
}

function markMailBody(doc, nodes, spans) {
  const groups = spans.map(() => [])
  let first = 0
  for (const { node, start, end } of nodes) {
    while (first < spans.length && spans[first][1] < start) first++
    const fragment = doc.createDocumentFragment()
    let offset = 0
    for (let i = first; i < spans.length && spans[i][0] <= end; i++) {
      const [a, b] = spans[i],
        empty = a === b
      if ((empty && (groups[i].length || a < start)) || (!empty && (b <= start || a >= end))) continue
      const left = Math.max(0, a - start),
        right = Math.min(end, b) - start
      fragment.append(doc.createTextNode(node.data.slice(offset, left)))
      const mark = doc.createElement('mark')
      mark.className = 'mailpilot-hit'
      mark.textContent = node.data.slice(left, right)
      fragment.append(mark)
      groups[i].push(mark)
      offset = right
    }
    if (fragment.childNodes.length) {
      fragment.append(doc.createTextNode(node.data.slice(offset)))
      node.replaceWith(fragment)
    }
  }
  return groups.filter((group) => group.length)
}
