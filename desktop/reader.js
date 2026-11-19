'use strict'
function createReader(root, cfg) {
  root.innerHTML = `
    <div id="reader-tools"><span id="location"></span><div id="reader-actions"></div></div>
    <div id="reader-scroll">
      <div id="reader-notice" role="status" hidden></div>
      <div class="reader-placeholder"><div class="empty-art"></div><h2 id="reader-prompt"></h2></div>
      <article id="letter" aria-label="邮件正文"></article>
    </div>
    <footer class="matchbar"><span class="match-query" id="expression"></span>
      <span id="match-count" role="status"></span><div id="match-actions"></div></footer>`
  root.querySelector('.empty-art').append(icon('book', 32))
  const warn = (e) => report(e, $('reader-notice'))
  const attachments = createAttachmentUI(warn)
  let query,
    message,
    format,
    bodyObserver,
    ticket = 0,
    external = false,
    groups = [],
    selected = -1
  function marked(key, index = 0, tag = 'span', cls = '') {
    const node = el(tag, cls),
      value = message.fields[key]?.[index] || ''
    markText(node, value, cfg.showHighlights ? message.marks[key]?.[index] : [], (mark) =>
      groups.push([mark])
    )
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
    if (e.key === 'F3' && query && !root.hidden && !attachments.isOpen()) {
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
    $('reader-notice').hidden = true
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
      head.append(attachments.cards(message, query, (i) => marked('attachment', i, 'b')))
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
              if (turn !== ticket) return
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
            if (e.isTrusted && /^(https?:|mailto:)/i.test(href)) api.link(href).catch(warn)
          })
          if (cfg.showHighlights && ['subject_body', 'all', 'full'].includes(query.mode)) {
            const { nodes, text } = visibleMailText(doc),
              matches = await api.mail('preview_marks', { ...query, text })
            if (turn !== ticket) return
            const found = markMailBody(doc, nodes, matches.marks.body?.[0] || [])
            groups.push(...found)
            if (matches.partial) warn(matches.partial)
            if ((message.marks.body?.[0]?.length || 0) > found.length)
              warn('部分匹配位于 Outlook 的纯文本表示，可点「纯文本」定位。')
          }
          firstMatch()
        } catch (e) {
          if (turn === ticket) warn(e)
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
        () => api.mail('open', { id: query.id, key: query.key }).catch(warn),
        'btn original'
      )
    )
    $('expression').replaceChildren(
      icon('find', 16),
      el('code', '', query.pattern),
      el('span', '', modes[query.mode])
    )
    if (message.partial || message.needsRefresh)
      warn(message.partial || '此邮件来自旧索引，刷新后可查看完整信头和原始格式。')
    updateCount()
  }
  function clear() {
    ++ticket
    query = message = null
    external = false
    groups = []
    selected = -1
    bodyObserver?.disconnect()
    attachments.reset()
    $('letter').replaceChildren()
    $('reader-actions').replaceChildren()
    $('location').replaceChildren()
    $('expression').replaceChildren()
    $('reader-notice').hidden = true
    root.dataset.state = 'empty'
    $('reader-prompt').textContent = '选择一封邮件，在此阅读'
    updateCount()
    api.images(false).catch(warn)
  }
  async function load(q) {
    clear()
    const turn = ticket
    query = q
    root.dataset.state = 'loading'
    $('reader-prompt').textContent = '正在读取邮件…'
    try {
      const result = await api.mail('detail', q)
      if (turn !== ticket) return
      message = result
      format = cfg.readerFormat
      $('reader-scroll').scrollTop = 0
      root.dataset.state = 'ready'
      draw()
    } catch (e) {
      if (turn !== ticket) return
      root.dataset.state = 'error'
      $('reader-prompt').textContent = '无法读取这封邮件'
      warn(e)
    }
  }
  function configure(next) {
    if (cfg.readerFormat !== next.readerFormat) format = next.readerFormat
    const redraw = ['readerFormat', 'expandHeaders', 'showHighlights', 'readerZoom', 'highlightColor'].some(
      (k) => cfg[k] !== next[k]
    )
    cfg = next
    if (message && redraw) draw()
  }
  $('match-actions').append(
    button('上一处匹配', 'prev', () => jump(-1), 'icon-btn', false),
    button('下一处匹配', 'next', () => jump(1), 'icon-btn', false)
  )
  document.addEventListener('keydown', navigateMatch)
  clear()
  return { clear, load, configure }
}

if (document.body.classList.contains('reader-page')) {
  async function initReaderWindow() {
    const data = await api.init()
    titlebar('邮件详情', data.source)
    applyLook(data.cfg)
    const reader = createReader($('reading-pane'), data.cfg)
    api.on('message', reader.load)
    api.on('settings', (d) => {
      applyLook(d.cfg)
      reader.configure(d.cfg)
    })
    if (data.query) await reader.load(data.query)
  }
  initReaderWindow().catch((e) => report(e, $('reader-notice')))
}
