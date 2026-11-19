'use strict'
const previewOrigin = 'mailpilot-preview://local'
const formats = {
  pdf: ['pdf'],
  word: ['docx', 'docm', 'doc'],
  sheet: ['xlsx', 'xlsm', 'xls', 'csv', 'tsv'],
  slides: ['pptx', 'pptm', 'ppt'],
  markdown: ['md', 'markdown'],
  image: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'ico'],
  text: ['txt', 'log', 'json', 'xml', 'yaml', 'yml', 'ini', 'css', 'js', 'html', 'htm', 'sql'],
}
function fileType({ name, type }) {
  let ext = name.includes('.') ? name.split('.').pop().toLowerCase() : ''
  let kind = Object.keys(formats).find((k) => formats[k].includes(ext))
  if (!kind) {
    // Mail clients sometimes give pasted pictures a display name without an extension.
    const image = /^image\/(png|jpeg|gif|webp|bmp|avif|x-icon|vnd\.microsoft\.icon)(?:\s*;|$)/i.exec(
      type || ''
    )
    if (image) {
      ext = image[1].toLowerCase()
      if (ext.endsWith('icon')) ext = 'ico'
      kind = 'image'
    }
  }
  return { ext, kind: kind || 'file' }
}
function fileSize(size) {
  if (size == null) return ''
  if (size < 1024) return size + ' B'
  return size < 1048576 ? +(size / 1024).toFixed(1) + ' KB' : +(size / 1048576).toFixed(1) + ' MB'
}
function fileBadge(file) {
  const { kind, ext } = fileType(file)
  const badge = el('span', 'file-badge ' + kind, (ext || 'FILE').toUpperCase().slice(0, 5))
  badge.setAttribute('aria-hidden', 'true')
  return badge
}
function createAttachmentUI(warn) {
  let files = [],
    currentMail,
    current = -1,
    generation = 0,
    iframe,
    payload,
    idleTimer,
    frameReady = false,
    fetching = false
  const modal = el('dialog', 'preview-dialog')
  modal.ariaLabel = '附件预览'
  const toolbar = el('div', 'preview-tools'),
    name = el('strong', 'preview-name'),
    position = el('span', 'preview-position'),
    fileHeading = el('div', 'preview-heading'),
    stage = el('div', 'preview-stage'),
    status = el('div', 'preview-status')
  const feedback = el('div', 'attachment-feedback')
  feedback.setAttribute('role', 'status')
  const menu = el('div', 'file-menu')
  menu.setAttribute('popover', 'auto')
  menu.setAttribute('role', 'menu')
  let invoker
  function showMenu(anchor, i, x, y) {
    if (menu.matches(':popover-open')) menu.hidePopover()
    invoker = anchor
    const items = [
      ['预览', 'eye', () => open(i)],
      ['下载', 'download', () => transfer('save', i)],
      ['复制', 'copy', () => transfer('copy', i)],
    ]
    menu.replaceChildren(
      ...items.map(([label, glyph, act]) => {
        const b = button(
          label,
          glyph,
          () => {
            menu.hidePopover()
            anchor.focus()
            return act()
          },
          'file-menu-item'
        )
        b.setAttribute('role', 'menuitem')
        return b
      })
    )
    menu.showPopover()
    const rect = anchor.getBoundingClientRect()
    menu.style.left = Math.max(4, Math.min(x ?? rect.left, innerWidth - menu.offsetWidth - 5)) + 'px'
    menu.style.top = Math.max(4, Math.min(y ?? rect.bottom + 3, innerHeight - menu.offsetHeight - 5)) + 'px'
    menu.firstChild.focus()
  }
  menu.onkeydown = (e) => {
    if (e.key === 'Escape') {
      menu.hidePopover()
      invoker?.focus()
      e.preventDefault()
    }
    if (['ArrowDown', 'ArrowUp'].includes(e.key)) {
      const buttons = [...menu.children],
        i = buttons.indexOf(document.activeElement)
      buttons[(i + (e.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length].focus()
      e.preventDefault()
    }
  }
  const busy = new Set()
  async function transfer(action, index) {
    const mail = currentMail
    const key = JSON.stringify([mail, action, index])
    if (busy.has(key)) return
    busy.add(key)
    const label = action === 'save' ? '下载' : '复制'
    feedback.textContent = '正在' + label + '…'
    try {
      const result = await api.attachment(action, { ...mail, index })
      if (mail !== currentMail) return
      feedback.textContent = result ? '已' + label + ' ' + result.count + ' 个附件' : ''
      if (result?.errors.length) warn(feedback.textContent + '。' + result.errors.join('；'))
    } catch (e) {
      if (mail === currentMail) {
        feedback.textContent = (e.message || String(e)).replace(/^.*?Error: /, '')
        if (!modal.open) warn(e)
      }
    } finally {
      busy.delete(key)
    }
  }
  const back = button('返回邮件', 'prev', () => modal.close(), 'btn')
  const prev = button('上一个附件', 'prev', () => open(current - 1), 'icon-btn', false),
    next = button('下一个附件', 'next', () => open(current + 1), 'icon-btn', false)
  const actions = el('div', 'preview-actions')
  actions.append(
    button('复制', 'copy', () => transfer('copy', current), 'btn'),
    button('下载', 'download', () => transfer('save', current), 'btn primary')
  )
  fileHeading.append(name, position)
  toolbar.append(back, fileHeading, prev, next, actions)
  status.setAttribute('role', 'status')
  modal.append(toolbar, stage, status)
  document.body.append(menu, modal)
  function send() {
    if (frameReady && payload) iframe.contentWindow.postMessage(payload, previewOrigin)
  }
  window.addEventListener('message', (e) => {
    if (e.origin !== previewOrigin || e.source !== iframe?.contentWindow) return
    if (e.data?.type === 'ready') {
      frameReady = true
      send()
    }
    if (!modal.open) return
    if (e.data?.type === 'close') modal.close()
    if (e.data?.type === 'step') open(current + Math.sign(e.data.delta))
  })
  function close() {
    generation++
    payload = null
    if (modal.open) modal.close()
    if (fetching) api.attachment('dismiss').catch(() => {})
    fetching = false
    if (iframe) {
      iframe.hidden = true
      if (frameReady) iframe.contentWindow.postMessage({ type: 'clear' }, previewOrigin)
      clearTimeout(idleTimer)
      idleTimer = setTimeout(() => {
        iframe?.remove()
        iframe = null
        frameReady = false
      }, 30000)
    }
    if (menu.matches(':popover-open')) menu.hidePopover()
    if (currentMail && document.querySelector('.attachment-section'))
      document.querySelector('.attachment-section').append(feedback)
  }
  modal.onclose = () => {
    if (!modal.open) close()
  }
  async function open(index) {
    if (!files[index]) return
    const ticket = ++generation
    clearTimeout(idleTimer)
    current = index
    const file = files[index],
      { kind, ext } = fileType(file)
    name.textContent = name.title = file.name
    position.textContent = [fileSize(file.size), '附件 ' + (index + 1) + ' / ' + files.length]
      .filter(Boolean)
      .join(' · ')
    prev.disabled = index === 0
    next.disabled = index + 1 === files.length
    modal.append(feedback)
    feedback.textContent = ''
    if (!modal.open) modal.showModal()
    status.hidden = false
    status.textContent = kind === 'file' ? '此格式可下载后查看。' : '正在打开附件…'
    payload = null
    if (iframe) iframe.hidden = true
    if (kind === 'file') {
      if (fetching) api.attachment('dismiss').catch(() => {})
      fetching = false
      return
    }
    if (!iframe) {
      iframe = el('iframe', 'attachment-viewer')
      iframe.title = '附件内容'
      iframe.hidden = true
      iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin')
      iframe.src = previewOrigin + '/viewer.html'
      stage.replaceChildren(iframe)
    }
    try {
      fetching = true
      const result = await api.attachment('preview', { ...currentMail, index })
      if (ticket !== generation) return
      payload = {
        type: 'open',
        kind,
        ext,
        url: result.url,
        size: result.size,
        theme: document.documentElement.dataset.theme,
      }
      iframe.hidden = false
      status.hidden = true
      send()
    } catch (e) {
      if (ticket === generation) status.textContent = (e.message || String(e)).replace(/^.*?Error: /, '')
    } finally {
      if (ticket === generation) fetching = false
    }
  }
  modal.onkeydown = (e) => {
    if (e.altKey && ['ArrowLeft', 'ArrowRight'].includes(e.key)) {
      e.preventDefault()
      open(current + (e.key === 'ArrowRight' ? 1 : -1))
    }
  }
  function cards(message, query, markedName) {
    files = message.fields.attachment.map((name, i) => ({ ...message.files[i], name }))
    if (currentMail?.key !== query.key || currentMail.stamp !== message.stamp) {
      currentMail = { id: query.id, key: query.key, stamp: message.stamp }
      feedback.textContent = ''
    }
    const section = el('section', 'attachment-section'),
      heading = el('div', 'attachment-heading')
    heading.append(
      icon('clip', 15),
      el('strong', '', '附件 · ' + files.length),
      button('下载全部', 'download', () => transfer('save', null), 'text-btn'),
      button('复制全部', 'copy', () => transfer('copy', null), 'text-btn')
    )
    const grid = el('div', 'attachments')
    const overflow = el('details', 'extra-attachments'),
      extraGrid = el('div', 'attachments')
    overflow.append(el('summary', '', '其余 ' + (files.length - 4) + ' 个附件'), extraGrid)
    files.forEach((file, i) => {
      const card = el('div', 'attachment'),
        info = el('span', 'attachment-info')
      info.append(markedName(i), el('small', '', fileSize(file.size)))
      const preview = button('预览 ' + file.name, null, () => open(i), 'attachment-open', false)
      preview.append(fileBadge(file), info)
      const more = button('附件选项：' + file.name, 'menu', () => showMenu(more, i), 'icon-btn', false)
      more.setAttribute('aria-haspopup', 'menu')
      card.oncontextmenu = (e) => {
        e.preventDefault()
        showMenu(more, i, e.clientX, e.clientY)
      }
      card.append(preview, more)
      ;(i < 4 ? grid : extraGrid).append(card)
      if (i >= 4 && message.marks.attachment?.[i]?.length) overflow.open = true
    })
    section.append(heading, grid)
    if (files.length > 4) section.append(overflow)
    if (!modal.open) section.append(feedback)
    return section
  }
  return {
    cards,
    reset() {
      close()
      currentMail = null
      files = []
    },
    isOpen: () => modal.open,
  }
}
