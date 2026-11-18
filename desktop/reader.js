'use strict'
let cfg,
  query,
  message,
  ticket = 0,
  format,
  external = false,
  groups = [],
  selected = -1,
  bodyObserver
function marked(key, index = 0, tag = 'span', cls = '') {
  const node = el(tag, cls),
    value = message.fields[key]?.[index] || ''
  markText(node, value, cfg.showHighlights ? message.marks[key]?.[index] : [], (mark) => groups.push([mark]))
  return node
}
function addField(parent, key) {
  const values = message.fields[key] || []
  if (!values.length) return
  const row = el('div', 'address-row'),
    content = el('div', 'field-values')
  row.append(el('span', 'field-label', fieldName(key)), content)
  values.forEach((_v, i) => {
    if (i) content.append(document.createTextNode('； '))
    content.append(marked(key, i))
  })
  parent.append(row)
}
function updateCount() {
  $('match-count').textContent = cfg?.showHighlights
    ? groups.length
      ? selected + 1 + ' / ' + groups.length + ' 处'
      : '0 处匹配'
    : '高亮已关闭'
  for (const b of $('match-actions').children) b.disabled = !groups.length
}
function jump(delta, scroll = true) {
  if (!groups.length) {
    selected = -1
    updateCount()
    return
  }
  groups[selected]?.forEach((m) => m.classList.remove('current'))
  selected = (selected + delta + groups.length) % groups.length
  const group = groups[selected]
  group.forEach((m) => m.classList.add('current'))
  if (scroll) {
    let parent = group[0].parentElement
    while (parent) {
      if (parent.tagName === 'DETAILS') parent.open = true
      parent = parent.parentElement
    }
    group[0].scrollIntoView({ block: 'center' })
  }
  updateCount()
}
function firstMatch() {
  jump(1, false)
  const mark = groups[0]?.[0]
  if (!cfg.jumpToMatch || !mark) return
  const box = mark.getBoundingClientRect(),
    frame = mark.ownerDocument.defaultView.frameElement
  const y = box.top + (frame ? frame.getBoundingClientRect().top : 0)
  const viewer = $('reader-scroll').getBoundingClientRect()
  if (y < viewer.top || y > viewer.bottom - 20) mark.scrollIntoView({ block: 'center' })
}
function navigateMatch(e) {
  if (e.key === 'F3') {
    e.preventDefault()
    jump(e.shiftKey ? -1 : 1)
  }
}
function displayName(s) {
  return s?.split(/\s*</)[0] || s || '（无发件人）'
}
function draw() {
  const turn = ++ticket
  bodyObserver?.disconnect()
  groups = []
  selected = -1
  const f = message.fields,
    letter = $('letter')
  letter.replaceChildren()
  $('notice').hidden = true
  $('location').replaceChildren(icon('folder', 15), el('span', '', f.folder?.[0] || '邮件'))
  const title = marked('subject', 0, 'h1', 'mail-title')
  if (!title.textContent) title.append('（无主题）')
  const head = el('header', 'mail-head')
  const author = el('div', 'author'),
    sender = f.sender?.[0] || ''
  const avatar = el('span', 'avatar', Array.from(displayName(sender).replace(/[（(]/, ''))[0] || '邮')
  const who = el('div', 'author-lines')
  who.append(el('span', 'field-label', '发件人'), marked('sender', 0, 'strong'))
  if (!sender) who.lastChild.textContent = '（无发件人）'
  author.append(avatar, who)
  const time = el('time', 'mail-date', formatDate(f.received?.[0] || f.sent?.[0], true))
  author.append(time)
  head.append(title, author)
  for (const key of ['onBehalf', 'to', 'cc', 'bcc', 'replyTo']) addField(head, key)
  const extraKeys = Object.keys(f).filter(
    (k) =>
      !['subject', 'sender', 'body', 'attachment', 'onBehalf', 'to', 'cc', 'bcc', 'replyTo'].includes(k) &&
      f[k].length
  )
  const details = el('details', 'metadata'),
    summary = el('summary', '', '邮件属性与 Internet 邮件头')
  details.append(summary)
  details.open = cfg.expandHeaders || extraKeys.some((k) => message.marks[k] && cfg.showHighlights)
  for (const key of extraKeys) addField(details, key)
  head.append(details)
  if (f.attachment?.length) {
    const attachments = el('div', 'attachments')
    f.attachment.forEach((name, i) => {
      const chip = el('div', 'attachment')
      chip.append(icon('files', 22))
      const info = el('div')
      info.append(marked('attachment', i, 'b'))
      const file = message.files[i],
        size = file?.size
      info.append(
        el(
          'small',
          '',
          [
            name.split('.').length > 1 ? name.split('.').pop().toUpperCase() : '附件',
            size != null ? (size < 1024 ? size + ' B' : Math.round((size / 1024) * 10) / 10 + ' KB') : '',
          ]
            .filter(Boolean)
            .join(' · ')
        )
      )
      chip.append(info)
      attachments.append(chip)
    })
    head.append(attachments)
  }
  letter.append(head)
  const body = el('section', 'mail-body')
  letter.append(body)
  const bar = el('div', 'body-format')
  if (message.html) {
    const toggle = button(
      format === 'plain' ? '原始格式' : '纯文本',
      'text',
      () => {
        format = format === 'plain' ? 'original' : 'plain'
        draw()
      },
      'text-btn'
    )
    bar.append(toggle)
  }
  if (format === 'plain' || !message.html) {
    body.append(marked('body', 0, 'pre', 'plain-body'))
    firstMatch()
  } else {
    const frame = el('iframe', 'rich-body')
    frame.title = '原始邮件正文'
    frame.setAttribute('sandbox', 'allow-same-origin')
    frame.referrerPolicy = 'no-referrer'
    const rendered = mailDocument(message, cfg, external)
    if (rendered.remote && !external)
      bar.prepend(
        button(
          '显示外部图片',
          'mail',
          async () => {
            await api.images(true)
            external = true
            draw()
          },
          'text-btn'
        )
      )
    frame.onload = async () => {
      try {
        if (turn !== ticket) return
        const doc = frame.contentDocument
        doc.addEventListener('keydown', navigateMatch)
        const resize = () => {
          if (turn === ticket) {
            const height = Math.ceil(doc.body.getBoundingClientRect().bottom + doc.defaultView.scrollY + 8)
            frame.style.height = Math.max(120, height) + 'px'
          }
        }
        bodyObserver = new ResizeObserver(resize)
        bodyObserver.observe(doc.body)
        resize()
        doc.addEventListener('click', (e) => {
          const link = e.target.closest('a')
          if (!link) return
          e.preventDefault()
          const href = link.getAttribute('href') || ''
          if (href.startsWith('#')) {
            doc.getElementById(href.slice(1))?.scrollIntoView()
            return
          }
          if (e.isTrusted && /^(https?:|mailto:)/i.test(href)) api.link(href).catch(report)
        })
        if (cfg.showHighlights && ['subject_body', 'all', 'full'].includes(query.mode)) {
          const { nodes, text } = visibleMailText(doc),
            matches = await api.mail('preview_marks', { ...query, text })
          if (turn !== ticket) return
          const found = markMailBody(doc, nodes, matches.marks.body?.[0] || [])
          groups.push(...found)
          if (matches.partial) report(matches.partial)
          if ((message.marks.body?.[0]?.length || 0) > found.length)
            report('部分匹配位于 Outlook 的纯文本表示，可点「纯文本」定位。')
        }
        firstMatch()
      } catch (e) {
        if (turn === ticket) report(e)
      }
    }
    frame.srcdoc = rendered.html
    body.append(frame)
  }
  const actions = $('reader-actions')
  actions.replaceChildren(
    bar,
    button(
      '在 Outlook 中打开',
      'pop',
      () => api.mail('open', { id: query.id, key: query.key }),
      'btn original'
    )
  )
  $('expression').replaceChildren(
    icon('find', 16),
    el('code', '', query.pattern),
    el('span', '', modes[query.mode])
  )
  if (message.partial || message.needsRefresh)
    report(message.partial || '此邮件来自旧索引，刷新后可查看完整信头和原始格式。')
  updateCount()
}
async function load(q) {
  const turn = ++ticket
  query = q
  message = null
  external = false
  groups = []
  selected = -1
  updateCount()
  bodyObserver?.disconnect()
  $('letter').replaceChildren()
  $('reader-actions').replaceChildren()
  $('notice').hidden = true
  await api.images(false)
  const result = await api.mail('detail', q)
  if (turn !== ticket) return
  message = result
  format = cfg.readerFormat
  $('reader-scroll').scrollTop = 0
  draw()
}
async function init() {
  const data = await api.init()
  cfg = data.cfg
  titlebar('邮件详情', data.source)
  applyLook(cfg)
  $('match-actions').append(
    button('上一处匹配', 'prev', () => jump(-1), 'icon-btn', false),
    button('下一处匹配', 'next', () => jump(1), 'icon-btn', false)
  )
  document.addEventListener('keydown', navigateMatch)
  api.on('message', (q) => load(q).catch(report))
  api.on('settings', (d) => {
    const previous = cfg
    cfg = d.cfg
    applyLook(cfg)
    if (previous.readerFormat !== cfg.readerFormat) format = cfg.readerFormat
    if (message) draw()
  })
  if (data.query) await load(data.query)
}
init().catch(report)
