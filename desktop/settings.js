'use strict'
let saved,
  draft,
  defaults,
  section = 'appearance',
  card
const sections = {
  appearance: ['外观与配色', 'palette'],
  reading: ['邮件阅读', 'book'],
  search: ['查找偏好', 'search'],
  windows: ['窗口与侧栏', 'dock'],
  mailbox: ['邮箱与索引', 'database'],
}
const keys = {
  appearance: [
    'theme',
    'palette',
    'accentColor',
    'highlightColor',
    'selectionColor',
    'density',
    'syncAiTheme',
  ],
  reading: [
    'readerFont',
    'readerSize',
    'readerZoom',
    'readerFormat',
    'expandHeaders',
    'showHighlights',
    'jumpToMatch',
  ],
  search: ['mode', 'caseSensitive', 'showSnippet', 'showFolder', 'limit', 'debounceMs', 'timeoutMs', 'defaultSort'],
  windows: ['searchLayout', 'readerLayout', 'aiLayout', 'dockSide', 'dockWidth'],
  mailbox: [
    'source',
    'storeScope',
    'indexDir',
    'autoRefresh',
    'refreshMinutes',
    'cacheMiB',
    'batchSize',
    'pauseMs',
    'chatDir',
    'clientId',
  ],
}
const descriptions = {
  appearance: '选择界面主题、图标配色和匹配高亮。',
  reading: '调整邮件详情的显示方式。',
  search: '设置查找范围与结果列表。',
  windows: '分别选择查找和 AI 助手的显示方式。',
  mailbox: '管理邮件来源、索引和 AI 助手的数据目录。',
}
const changed = () =>
  Object.fromEntries(
    Object.keys(defaults)
      .filter((k) => draft[k] !== saved[k])
      .map((k) => [k, draft[k]])
  )
function dirty() {
  const count = Object.keys(changed()).length
  $('save').disabled = !count
  $('notice').textContent = count ? '有 ' + count + ' 项更改待保存' : '设置已同步'
}
function change(k, v) {
  draft[k] = v
  applyLook(draft)
  dirty()
  preview()
}
function group(title, caption) {
  card = el('section', 'settings-card')
  card.append(el('h3', '', title))
  if (caption) card.append(el('p', 'group-note', caption))
  $('settings-content').append(card)
}
function row(key, label, control, help) {
  const wrap = el('div', 'setting-row'),
    left = el('div', 'setting-label')
  const name = el('label', '', label)
  name.htmlFor = key
  left.append(name)
  if (help) left.append(el('small', '', help))
  control.id = key
  control.setAttribute('aria-label', label)
  wrap.append(left, control)
  card.append(wrap)
  return wrap
}
function select(k, label, choices, help) {
  const input = el('select')
  for (const [v, n] of Object.entries(choices)) input.append(option(v, n))
  input.value = draft[k]
  input.onchange = () => change(k, input.value)
  row(k, label, input, help)
}
function check(k, label, help) {
  const input = el('input', 'switch')
  input.type = 'checkbox'
  input.checked = draft[k]
  input.onchange = () => change(k, input.checked)
  row(k, label, input, help)
}
function number(k, label, min, max, unit) {
  const wrap = el('div', 'unit-input'),
    input = el('input')
  input.type = 'number'
  input.min = min
  input.max = max
  input.step = 1
  input.value = draft[k]
  input.oninput = () => change(k, input.value === '' ? NaN : Number(input.value))
  wrap.append(input, el('span', '', unit))
  row(k + '-control', label, wrap)
  input.id = k
  input.ariaLabel = label
  wrap.parentNode.querySelector('label').htmlFor = k
}
function pathRow(k, label) {
  const wrap = el('div', 'path-input'),
    input = el('input')
  input.value = draft[k]
  input.oninput = () => change(k, input.value)
  wrap.append(
    input,
    button(
      '浏览目录',
      'folder',
      async () => {
        const p = await api.directory(input.value)
        if (p) {
          input.value = p
          change(k, p)
        }
      },
      'icon-btn',
      false
    )
  )
  row(k + '-control', label, wrap).classList.add('stacked')
  input.id = k
  input.ariaLabel = label
  wrap.parentNode.querySelector('label').htmlFor = k
}
function color(k, label, fallback, canReset) {
  const wrap = el('div', 'color-input'),
    input = el('input'),
    code = el('code', '', draft[k] || '自动')
  input.type = 'color'
  input.value = draft[k] || fallback
  input.oninput = () => {
    change(k, input.value)
    code.textContent = input.value
  }
  wrap.append(code, input)
  if (canReset)
    wrap.append(
      button(
        '跟随配色',
        'reset',
        () => {
          change(k, '')
          render()
        },
        'icon-btn',
        false
      )
    )
  row(k + '-control', label, wrap)
  input.id = k
  input.ariaLabel = label
  wrap.parentNode.querySelector('label').htmlFor = k
}
function preview() {
  const area = $('style-preview')
  if (!area) return
  const mark = el('mark', '', 'PO-123456'),
    sample = el('div', 'sample-snip', '请核对订单 ')
  sample.append(mark)
  area.replaceChildren(icon('mail', 20), el('div', 'sample-title', '采购部 · 订单确认'), sample)
}
function appearance() {
  group('界面主题')
  const themes = el('div', 'theme-grid')
  for (const [key, label] of Object.entries({
    system: '跟随系统',
    light: '薄荷浅色',
    paper: '暖纸',
    dark: '墨蓝深色',
  })) {
    const b = button(
      label,
      null,
      () => {
        change('theme', key)
        render()
      },
      'theme-choice',
      false
    )
    b.dataset.choice = key
    b.setAttribute('aria-pressed', String(draft.theme === key))
    const thumb = el('span', 'theme-thumb ' + key)
    thumb.append(el('i'), el('i'), el('i'))
    b.append(thumb, el('span', '', label))
    themes.append(b)
  }
  card.append(themes)
  check('syncAiTheme', 'AI 助手跟随此外观')
  group('图标与界面配色')
  const grid = el('div', 'palette-grid')
  for (const [key, [name, ink, accent, pale]] of Object.entries(palettes)) {
    const b = button(
      name,
      null,
      () => {
        change('palette', key)
        render()
      },
      'palette-choice',
      false
    )
    b.dataset.palette = key
    b.setAttribute('aria-pressed', String(draft.palette === key))
    const swatches = el('span', 'swatches')
    for (const c of [ink, accent, pale]) {
      const s = el('i')
      s.style.background = c
      swatches.append(s)
    }
    const arts = el('span', 'palette-arts')
    for (const id of ['search', 'ai', 'settings']) {
      const img = el('img')
      img.alt = ''
      img.src = 'icons/' + key + '-' + id + '.png'
      arts.append(img)
    }
    b.append(swatches, arts, el('b', '', name))
    grid.append(b)
  }
  card.append(grid)
  group('颜色与列表')
  color('accentColor', '强调色', palettes[draft.palette][2], true)
  color('selectionColor', '选中背景', palettes[draft.palette][3], true)
  color('highlightColor', '匹配高亮', '#ffe49a', false)
  select('density', '列表密度', { compact: '紧凑', comfortable: '标准', spacious: '宽松' })
  const box = el('div', 'style-preview')
  box.id = 'style-preview'
  box.setAttribute('aria-label', '查找结果预览')
  card.append(box)
  preview()
}
function reading() {
  group('正文')
  select('readerFormat', '默认阅读格式', { original: '原始格式', plain: '纯文本' })
  number('readerZoom', '原始邮件缩放', 70, 180, '%')
  const font = el('input')
  font.value = draft.readerFont
  font.maxLength = 80
  font.oninput = () => change('readerFont', font.value)
  const fonts = ['Microsoft YaHei UI', '等线', '宋体', 'Calibri', 'Segoe UI', 'Consolas']
  const list = el('select')
  for (const f of fonts) list.append(option(f, f))
  list.append(option('', '自定义字体…'))
  list.value = fonts.includes(draft.readerFont) ? draft.readerFont : ''
  row('fontChoice', '纯文本字体', list)
  const custom = row('readerFont', '自定义字体名称', font)
  custom.hidden = !!list.value
  list.onchange = () => {
    custom.hidden = !!list.value
    if (list.value) {
      font.value = list.value
      change('readerFont', list.value)
    } else { font.focus(); font.select() }
  }
  number('readerSize', '纯文字号', 11, 26, 'px')
  group('信头与匹配')
  check('expandHeaders', '默认展开邮件属性', '显示邮件头、类别、会话 ID 等信息。')
  check('showHighlights', '显示匹配高亮', '应用到结果片段和邮件详情。')
  check('jumpToMatch', '打开时定位到首处匹配')
}
function searchSettings() {
  group('匹配规则')
  select('mode', '默认范围', modes)
  check('caseSensitive', '默认区分大小写')
  number('debounceMs', '停止输入后查找', 100, 2000, 'ms')
  number('timeoutMs', '单字段匹配时限', 5, 500, 'ms')
  group('结果列表')
  select('defaultSort', '默认排序', sortModes)
  check('showSnippet', '显示匹配片段')
  check('showFolder', '显示文件夹路径')
  number('limit', '每页结果数', 1, 1000, '封')
}
function windows() {
  group('显示方式')
  const choices = { window: '独立窗口', sidebar: '侧边栏' }
  select('searchLayout', '正则查找', choices)
  select('readerLayout', '邮件详情', { pane: '在查找窗口右侧预览', window: '独立窗口' }, '查找停靠到侧边栏时，邮件详情始终使用独立窗口。')
  select('aiLayout', 'AI 助手', choices)
  group('侧边栏位置', '经典 Outlook 使用任务窗格。新版 Outlook 使用跟随邮件窗口的贴边侧栏。')
  select('dockSide', '停靠位置', { left: '左侧', right: '右侧' })
  number('dockWidth', '侧栏宽度', 300, 800, 'px')
}
function mailbox() {
  group('邮箱来源')
  select('source', '独立启动时使用', { classic: '经典 Outlook', graph: '新版 Outlook' })
  select('storeScope', '经典 Outlook 邮箱', { default: '默认邮箱', all: '所有已挂载邮箱和 PST' })
  const id = el('input')
  id.value = draft.clientId
  id.placeholder = 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
  id.oninput = () => change('clientId', id.value)
  row('clientId', 'Microsoft 应用 ID', id, '新版 Outlook 使用委托的 Mail.Read 权限。').classList.add(
    'stacked'
  )
  const connect = button(
    '连接 Microsoft 邮箱',
    'pop',
    async () => {
      await save()
      connect.disabled = true
      try {
        await api.login()
        $('notice').textContent = '邮箱已连接'
      } finally {
        connect.disabled = false
      }
    },
    'btn'
  )
  card.append(connect)
  group('索引与刷新')
  pathRow('indexDir', '本地索引目录')
  check('autoRefresh', '打开窗口时按需刷新')
  number('refreshMinutes', '自动刷新间隔', 1, 1440, '分钟')
  number('batchSize', '每批邮件数', 8, 256, '封')
  number('pauseMs', '批间休息', 0, 1000, 'ms')
  number('cacheMiB', '每个索引连接缓存', 1, 64, 'MiB')
  group('AI 助手')
  pathRow('chatDir', '会话与模型配置目录')
  card.append(button('打开 AI 助手', 'ai', () => api.launch('ai'), 'btn'))
}
function render() {
  const content = $('settings-content')
  content.replaceChildren(
    el('h2', 'settings-heading', sections[section][0]),
    el('p', 'section-description', descriptions[section])
  )
  for (const b of $('sections').children)
    b.setAttribute('aria-current', b.dataset.section === section ? 'page' : 'false')
  ;({ appearance, reading, search: searchSettings, windows, mailbox })[section]()
  content.append(
    button(
      '恢复本页默认设置',
      'reset',
      () => {
        for (const k of keys[section]) draft[k] = defaults[k]
        render()
        dirty()
      },
      'text-btn reset-page'
    )
  )
  applyLook(draft)
}
async function save() {
  const patch = changed()
  if (Object.keys(patch).length) {
    saved = await api.save(patch)
    draft = { ...saved }
  }
  dirty()
  $('notice').textContent = '设置已保存'
}
async function init() {
  const d = await api.init()
  saved = d.cfg
  draft = { ...saved }
  defaults = d.defaults
  titlebar('偏好设置')
  for (const [key, [label, glyph]] of Object.entries(sections)) {
    const b = button(
      label,
      glyph,
      () => {
        section = key
        render()
        $('settings-scroll').scrollTop = 0
      },
      'section-link'
    )
    b.dataset.section = key
    $('sections').append(b)
  }
  $('cancel').onclick = () => api.window('close')
  $('save').onclick = () => save().catch(report)
  api.on('settings', (data) => {
    const local = changed()
    saved = data.cfg
    draft = { ...saved, ...local }
    dirty()
    render()
  })
  render()
  dirty()
}
init().catch(report)
