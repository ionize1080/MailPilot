'use strict'
let cfg,
  source,
  tick,
  poll,
  generation = 0,
  cursor = null,
  hits = [],
  searched,
  lastSync,
  polling = false,
  lastCount,
  reader,
  selection
const input = $('pattern'),
  scope = $('mode'),
  folder = $('folder'),
  caseButton = $('case')
const dock = button('收纳为侧边栏', 'dock', () => api.window('dock'), 'dock-button')
const splitter = $('splitter')
function listWidth(pixels) {
  const area = document.querySelector('.app-body').clientWidth - $('rail').offsetWidth
  const width = Math.max(280, Math.min(area - 310, pixels))
  document.body.style.setProperty('--list-width', width + 'px')
  splitter.setAttribute('aria-valuenow', Math.round((100 * width) / area))
}
splitter.onpointerdown = (e) => {
  if (e.button === 0) splitter.setPointerCapture(e.pointerId)
}
splitter.onpointermove = (e) => {
  if (splitter.hasPointerCapture(e.pointerId)) listWidth(e.clientX - $('rail').getBoundingClientRect().right)
}
splitter.ondblclick = () => {
  document.body.style.removeProperty('--list-width')
  splitter.setAttribute('aria-valuenow', '35')
}
splitter.onkeydown = (e) => {
  if (['ArrowLeft', 'ArrowRight'].includes(e.key)) {
    e.preventDefault()
    listWidth(document.querySelector('.workspace').offsetWidth + (e.key === 'ArrowRight' ? 20 : -20))
  }
}
splitter.setAttribute('aria-valuenow', '35')
function layout(mode) {
  document.body.dataset.layout = mode
  const floating = mode === 'window'
  const label = floating ? '收纳为侧边栏' : '独立窗口'
  dock.replaceChildren(icon(floating ? 'dock' : 'pop', 16), el('span', '', label))
  dock.title = dock.ariaLabel = label
  const pane = $('reading-pane')
  const show = floating && cfg.readerLayout === 'pane'
  splitter.hidden = !show
  if (pane.hidden === show) {
    pane.hidden = !show
    if (show && selection) reader.load(selection)
    else reader.clear()
  }
}
function setCase(value) {
  caseButton.setAttribute('aria-pressed', String(value))
}
function args() {
  return {
    pattern: input.value,
    mode: scope.value,
    caseSensitive: caseButton.getAttribute('aria-pressed') === 'true',
    folder: folder.value,
    limit: cfg.limit,
    sort: $('sort').value,
  }
}
function empty(title, caption, examples) {
  const node = el('div', 'empty'),
    art = el('div', 'empty-art')
  art.append(icon(examples ? 'find' : 'mail', 32))
  node.append(art, el('h3', '', title), el('p', '', caption))
  if (examples) {
    const chips = el('div', 'example-chips')
    for (const [label, pattern, mode] of [
      ['订单号', 'PO-\\d{6}', 'subject'],
      ['Excel 附件', '\\.xlsx?$', 'attachment'],
      ['发件域名', '@example\\.com', 'sender'],
    ]) {
      chips.append(
        button(
          label,
          null,
          () => {
            input.value = pattern
            scope.value = mode
            run(false)
            input.focus()
          },
          'chip'
        )
      )
    }
    node.append(chips)
  }
  $('results').replaceChildren(node)
}
function clear(keepSelection = false) {
  if (!keepSelection && selection) {
    reader.clear()
    selection = null
  }
  hits = []
  cursor = null
  searched = null
  $('more').hidden = true
  $('count').hidden = true
  $('timing').textContent = ''
  $('notice').hidden = true
  $('results').replaceChildren()
  if (!input.value) empty('从一个表达式开始', '直接输入正则，或选择一个示例。', true)
}
function resultRow(hit) {
  const row = el('button', 'result-row')
  row.type = 'button'
  row.dataset.key = hit.key
  row.classList.toggle('selected', selection?.key === hit.key)
  if (selection?.key === hit.key) row.setAttribute('aria-current', 'true')
  const art = el('span', 'row-icon')
  art.append(icon(hit.field === 'attachment' ? 'clip' : 'mail'))
  const content = el('span', 'result-content'),
    head = el('span', 'result-top'),
    title = el('strong', 'subject')
  markText(
    title,
    hit.subject || '（无主题）',
    cfg.showHighlights && hit.field === 'subject' && hit.fieldSpan ? [hit.fieldSpan] : []
  )
  const stamp = el('time', '', formatDate(hit.received))
  head.append(title, stamp)
  content.append(head)
  const meta = el('span', 'result-meta'),
    sender = el('span', 'sender')
  markText(
    sender,
    hit.sender || '（无发件人）',
    cfg.showHighlights && hit.field === 'sender' && hit.fieldSpan && hit.fieldSpan[1] <= hit.sender.length
      ? [hit.fieldSpan]
      : []
  )
  meta.append(sender)
  if (cfg.showFolder && hit.folder) meta.append(el('span', 'folder-path', hit.folder))
  content.append(meta)
  const preview = el('span', 'snippet'),
    field = el('span', 'field-tag', fieldName(hit.field))
  preview.append(field)
  if (cfg.showSnippet) {
    const snip = el('span', 'snippet-text')
    markText(snip, hit.snippet, cfg.showHighlights && hit.span ? [hit.span] : [])
    preview.append(snip)
  }
  content.append(preview)
  row.append(art, content)
  row.onclick = () => {
    if (
      selection?.key === hit.key &&
      !$('reading-pane').hidden &&
      $('reading-pane').dataset.state === 'ready'
    )
      return
    const previous = document.querySelector('.result-row.selected')
    previous?.classList.remove('selected')
    previous?.removeAttribute('aria-current')
    row.classList.add('selected')
    row.setAttribute('aria-current', 'true')
    selection = { id: hit.id, key: hit.key, ...searched }
    if ($('reading-pane').hidden) api.read(selection).catch(report)
    else reader.load(selection)
  }
  return row
}
function render(append) {
  if (append) $('results').append(...append.map(resultRow))
  else $('results').replaceChildren(...hits.map(resultRow))
  $('count').hidden = false
  $('count').textContent = hits.length + (cursor ? '+' : '')
  $('more').hidden = !cursor
  if (!hits.length)
    empty(
      '没有匹配的邮件',
      scope.value === 'full'
        ? '可以调整表达式，或选择其他文件夹。'
        : '可以切换到「全文」，或调整表达式和文件夹。',
      false
    )
}
function schedule() {
  clearTimeout(tick)
  generation++
  clear()
  if (input.value) {
    $('timing').textContent = '等待查找…'
    tick = setTimeout(() => run(false), cfg.debounceMs)
  }
}
async function run(more, keepSelection = false) {
  clearTimeout(tick)
  if (!input.value) {
    clear()
    return
  }
  const ticket = ++generation,
    request = args()
  if (!more) clear(keepSelection)
  $('timing').textContent = '正在查找…'
  $('more').disabled = true
  try {
    const result = await api.mail('search_mail', { ...request, cursor: more ? cursor : null })
    if (ticket !== generation) return
    searched = request
    hits = more ? hits.concat(result.items) : result.items
    if (keepSelection && selection && !hits.some((hit) => hit.key === selection.key)) {
      reader.clear()
      selection = null
    }
    cursor = result.next
    render(more ? result.items : null)
    $('timing').textContent = result.ms + ' ms'
    if (result.partial) report(result.partial)
  } catch (e) {
    if (ticket === generation) {
      clear()
      $('timing').textContent = '查找未完成'
      report(e)
    }
  } finally {
    if (ticket === generation) $('more').disabled = false
  }
}
async function folders() {
  const previous = folder.value,
    list = await api.mail('list_folders')
  folder.replaceChildren(
    option('', '全部文件夹'),
    ...list.map((f) => option(f.folder, f.folder + ' · ' + f.count))
  )
  if (list.some((f) => f.folder === previous)) folder.value = previous
}
async function status() {
  if (polling) return
  polling = true
  try {
    const s = await api.mail('index_status'),
      sync = s.sync || {}
    $('status').textContent =
      '已索引 ' +
      s.count.toLocaleString() +
      ' 封' +
      (sync.active ? ' · 已检查 ' + (sync.checked || 0) + ' 封' : '') +
      (sync.error ? ' · ' + sync.error : '') +
      (sync.errors ? ' · ' + sync.errors + ' 封读取失败' : '')
    $('status').title = s.lastSync
      ? '上次刷新 ' + formatDate(new Date(s.lastSync * 1000).toISOString())
      : '尚未完成首次刷新'
    $('pause').hidden = !sync.active
    $('refresh').hidden = !!sync.active
    if (lastCount !== s.count || lastSync !== s.lastSync) {
      await folders()
      if (lastCount !== undefined && input.value) schedule()
    }
    lastCount = s.count
    lastSync = s.lastSync
  } catch (e) {
    $('status').textContent = (e.message || '').replace(/^.*?Error: /, '')
  } finally {
    polling = false
  }
}
async function init() {
  const data = await api.init()
  cfg = data.cfg
  source = data.source
  reader = createReader($('reading-pane'), cfg)
  titlebar('查找', source, [dock])
  layout(data.layout)
  const rail = $('rail')
  rail.append(
    button('正则查找', 'search', () => input.focus(), 'rail-btn active'),
    button('AI 助手', 'ai', () => api.launch('ai'), 'rail-btn'),
    el('div', 'spacer'),
    button('设置', 'settings', () => api.launch('settings'), 'rail-btn')
  )
  const hints = {
    subject: '仅匹配邮件标题',
    subject_body: '分别匹配标题和正文',
    all: '分别匹配标题、正文和附件名',
    attachment: '逐个匹配附件文件名',
    sender: '匹配发件人及实际代发人的姓名、邮箱',
    full: '匹配邮件所有已索引字段，包括收件人、抄送、密送、邮件头及附件名',
  }
  for (const [value, name] of Object.entries(modes)) {
    const o = option(value, name)
    o.title = hints[value]
    scope.append(o)
  }
  scope.addEventListener('change', () => {
    scope.title = hints[scope.value]
  })
  scope.title = hints[cfg.mode]
  scope.value = cfg.mode
  for (const [key, label] of Object.entries(sortModes)) $('sort').append(option(key, label))
  $('sort').value = cfg.defaultSort
  $('sort').onchange = () => run(false, true)
  setCase(cfg.caseSensitive)
  applyLook(cfg)
  clear()
  $('query').onsubmit = (e) => {
    e.preventDefault()
    run(false)
  }
  input.oninput = scope.onchange = folder.onchange = schedule
  caseButton.onclick = () => {
    setCase(caseButton.getAttribute('aria-pressed') !== 'true')
    schedule()
  }
  $('more').onclick = () => run(true)
  $('results').onkeydown = (e) => {
    const row = e.target.closest('.result-row')
    if (!row || !['ArrowDown', 'ArrowUp'].includes(e.key)) return
    e.preventDefault()
    const next = e.key === 'ArrowDown' ? row.nextElementSibling : row.previousElementSibling
    if (next) {
      next.focus()
      if (!$('reading-pane').hidden) next.click()
    }
  }
  for (const [id, label, glyph] of [
    ['refresh', '刷新索引', 'refresh'],
    ['pause', '暂停索引', 'pause'],
  ]) {
    const b = button(
      label,
      glyph,
      async () => {
        await api.mail(id)
        await status()
      },
      'foot-btn'
    )
    b.id = id
    b.hidden = id === 'pause'
    $('sync-actions').append(b)
  }
  api.on('layout', layout)
  api.on('settings', (d) => {
    const old = cfg
    cfg = d.cfg
    source = d.source
    applyLook(cfg)
    if (d.reset) clear()
    reader.configure(cfg)
    layout(document.body.dataset.layout)
    document.querySelector('.source').lastChild.textContent = sourceName(source)
    if (old.mode !== cfg.mode) scope.value = cfg.mode
    if (old.caseSensitive !== cfg.caseSensitive) setCase(cfg.caseSensitive)
    if (old.defaultSort !== cfg.defaultSort) $('sort').value = cfg.defaultSort
    if (d.reset) {
      lastCount = undefined
      folder.replaceChildren(option('', '全部文件夹'))
      api.mail('auto').catch(report)
      status()
    }
    if (
      old.mode !== cfg.mode ||
      old.caseSensitive !== cfg.caseSensitive ||
      d.reset ||
      old.limit !== cfg.limit ||
      old.defaultSort !== cfg.defaultSort
    )
      schedule()
    else if (searched) render()
  })
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey && e.key === 'f') || ((e.ctrlKey || e.metaKey) && e.key === 'l')) {
      e.preventDefault()
      input.focus()
      input.select()
    }
  })
  input.focus()
  await api.mail('auto').catch(report)
  await status()
  poll = setInterval(status, 2200)
}
init().catch(report)
