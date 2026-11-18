'use strict'
const api = window.mailpilot
const $ = (id) => document.getElementById(id)
const modes = {
  subject: '标题',
  subject_body: '标题与正文',
  all: '内容与附件',
  attachment: '附件名',
  sender: '发件人',
  full: '全文',
}
const fields = {
  subject: '标题',
  sender: '发件人',
  onBehalf: '实际发件人',
  to: '收件人',
  cc: '抄送',
  bcc: '密送',
  replyTo: '回复至',
  body: '正文',
  attachment: '附件名',
  received: '接收时间',
  sent: '发送时间',
  folder: '文件夹',
  categories: '类别',
  headers: 'Internet 邮件头',
  created: '创建时间',
  modified: '修改时间',
  expires: '到期时间',
  due: '截止时间',
  start: '开始时间',
  reminder: '提醒时间',
  completed: '完成时间',
  importance: '重要性',
  sensitivity: '敏感度',
  size: '邮件大小（字节）',
  status: '邮件状态',
  messageId: '邮件 ID',
  conversation: '会话主题',
  conversationId: '会话 ID',
  conversationIndex: '会话索引',
  inReplyTo: '回复邮件 ID',
  references: '引用邮件 ID',
  link: 'Outlook 链接',
  flag: '后续标志',
  voting: '投票选项',
  vote: '投票答复',
  billing: '计费信息',
  companies: '公司',
  class: '邮件类型',
  classification: '收件箱分类',
  attachmentType: '附件类型',
  attachmentSize: '附件大小（字节）',
  contentId: '内嵌内容 ID',
  attachmentLocation: '附件位置',
}
Object.assign(fields, {
  links: '正文链接',
  imageAlt: '图片说明',
  receivedBy: '实际收件人',
  receivedFor: '代收邮箱',
  recipientId: '收件人标识',
  flagIcon: '标志颜色',
})
const fieldName = (key) => fields[key] || key.replace(/^custom:/, '')
const palettes = {
  jade: ['翡翠', '#26534a', '#23997d', '#c9eae0'],
  ocean: ['海蓝', '#2b4370', '#4671d6', '#d3dff9'],
  graphite: ['石墨', '#313843', '#515e6f', '#d8dee4'],
}
const paths = {
  search: 'M20 20l-5-5 M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z',
  ai: 'm13 3 2.3 5.7L21 11l-5.7 2.3L13 19l-2.3-5.7L5 11l5.7-2.3L13 3Z M5 15l.9 2.1L8 18l-2.1.9L5 21l-.9-2.1L2 18l2.1-.9Z',
  settings:
    'M4 6h6m4 0h6M4 12h11m4 0h1M4 18h2m4 0h10 M14 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm5 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm-9 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
  mail: 'M3 6h18v13H3z M3 7l9 7 9-7',
  folder: 'M3 7V5h6l3 3h9v11H3z',
  dock: 'M3 4h18v16H3z M14.5 4v16',
  pop: 'M14 3h7v7 M21 3l-9 9 M10 5H4v15h15v-6',
  min: 'M5 12h14',
  max: 'M5 5h14v14H5z',
  close: 'M6 6l12 12M18 6 6 18',
  sun: 'M12 5V2m0 20v-3M5 12H2m20 0h-3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  book: 'M3 5c3-1 6-1 9 1 3-2 6-2 9-1v14c-3-1-6-1-9 1-3-2-6-2-9-1z M12 7v12',
  refresh: 'M20 5v5h-5 M4 19v-5h5 M5.3 9a7.2 7.2 0 0 1 12-3l2.7 3 M4 15l2.7 3a7.2 7.2 0 0 0 12-3',
  pause: 'M8 5v14M16 5v14',
  next: 'm9 5 7 7-7 7',
  prev: 'm15 5-7 7 7 7',
  down: 'm5 9 7 7 7-7',
  check: 'm4 12 5 5L20 6',
  enter: 'M19 5v9H5m4-4-4 4 4 4',
  files: 'M9 3h7l4 4v14H6V3z M15 3v5h5 M9 13h8m-8 3h6',
  clip: 'm7 13 8-8a3 3 0 0 1 4 4L8 20a4.3 4.3 0 0 1-6-6L13 3 M6 15l9-9',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2',
  filter: 'M3 5h18l-7 8v5l-4 2v-7z',
  database: 'M20 6c0 4-16 4-16 0s16-4 16 0ZM4 6v12c0 4 16 4 16 0V6M4 12c0 4 16 4 16 0',
  reset: 'M4 4v6h6M4 9a8 8 0 1 1 .5 7',
  user: 'M16 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 20a8 8 0 0 1 16 0',
  text: 'M3 5h18v3m-9-3v15m-4 0h8',
  palette: 'M21 11c0 5-7 1-7 5 0 2 2 4-2 5a9 9 0 1 1 9-10ZM7 10h.1M10 6.5h.1M15 7h.1',
  find: 'M4 7h8M4 12h4M4 17h4 M19 14a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm-1 3 4 4',
}
function icon(key, size = 18) {
  const ns = 'http://www.w3.org/2000/svg',
    svg = document.createElementNS(ns, 'svg'),
    p = document.createElementNS(ns, 'path')
  for (const [k, v] of Object.entries({
    viewBox: '0 0 24 24',
    width: size,
    height: size,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': 1.65,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    'aria-hidden': true,
  }))
    svg.setAttribute(k, v)
  p.setAttribute('d', paths[key])
  svg.append(p)
  return svg
}
function el(tag, cls, text) {
  const node = document.createElement(tag)
  if (cls) node.className = cls
  if (text != null) node.textContent = text
  return node
}
function button(label, glyph, action, cls = 'btn', text = true) {
  const b = el('button', cls)
  b.type = 'button'
  b.title = label
  b.setAttribute('aria-label', label)
  if (glyph) b.append(icon(glyph))
  if (text) b.append(el('span', '', label))
  b.onclick = async () => {
    try {
      await action()
    } catch (e) {
      report(e)
    }
  }
  return b
}
const sourceName = (code) => (code === 'graph' ? '新版 Outlook' : '经典 Outlook')
function contrastInk(hex) {
  const linear = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((n) => (n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4))
  const light = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
  return 1.05 / (light + 0.05) > (light + 0.05) / 0.062 ? '#ffffff' : '#182222'
}
function applyLook(cfg) {
  const root = document.documentElement,
    colors = palettes[cfg.palette] || palettes.jade
  root.dataset.theme = cfg.theme
  root.dataset.density = cfg.density
  const tokens = {
    '--ink-accent': colors[1],
    '--brand': colors[2],
    '--pale': colors[3],
    '--highlight': cfg.highlightColor,
    '--accent-override': cfg.accentColor,
    '--selection-override': cfg.selectionColor,
    '--highlight-ink': contrastInk(cfg.highlightColor),
    '--custom-button-ink': cfg.accentColor ? contrastInk(cfg.accentColor) : '',
    '--selected-ink': cfg.selectionColor ? contrastInk(cfg.selectionColor) : '',
    '--reader-size': cfg.readerSize + 'px',
    '--reader-font': JSON.stringify(cfg.readerFont),
  }
  for (const [k, v] of Object.entries(tokens)) root.style.setProperty(k, v)
  document.querySelectorAll('img[data-art]').forEach((img) => {
    img.src = 'icons/' + cfg.palette + '-' + img.dataset.art + '.png'
  })
}
function report(e) {
  const message = (e?.message || String(e)).replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '')
  const node = $('notice')
  if (node) {
    node.textContent = message
    node.hidden = false
  }
}
function titlebar(label, source, controls = []) {
  const bar = $('titlebar'),
    brand = el('div', 'wordmark'),
    img = el('img')
  img.dataset.art = 'brand'
  img.alt = ''
  brand.append(img, el('b', '', 'MailPilot'), el('i', 'title-separator'), el('span', 'caption', label))
  bar.append(brand)
  if (source) {
    const badge = el('span', 'source')
    badge.append(icon('mail', 14), sourceName(source))
    bar.append(badge)
  }
  const actions = el('div', 'window-actions')
  actions.append(
    ...controls,
    button('最小化', 'min', () => api.window('minimize'), 'chrome', false),
    button('最大化或还原', 'max', () => api.window('maximize'), 'chrome maximize', false),
    button('关闭', 'close', () => api.window('close'), 'chrome close', false)
  )
  bar.append(actions)
  bar.ondblclick = (e) => {
    if (!e.target.closest('button')) api.window('maximize')
  }
}
function option(value, label) {
  const o = el('option', '', label)
  o.value = value
  return o
}
function formatDate(value, long = false) {
  const d = new Date(value)
  if (!value || Number.isNaN(+d)) return value || ''
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: long ? 'long' : '2-digit',
    day: 'numeric',
    ...(long ? { weekday: 'long' } : {}),
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(d)
}
function markText(container, text, spans = [], visit) {
  let offset = 0
  for (const [start, end] of spans) {
    container.append(document.createTextNode(text.slice(offset, start)))
    const mark = el('mark', start === end ? 'zero' : '', text.slice(start, end))
    container.append(mark)
    if (visit) visit(mark)
    offset = end
  }
  container.append(document.createTextNode(text.slice(offset)))
}
