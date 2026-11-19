'use strict'
const fs = require('node:fs')
const path = require('node:path')
const { randomUUID } = require('node:crypto')
const root = path.resolve(__dirname, '..')
const home = process.env.MAILPILOT_HOME || path.join(process.env.LOCALAPPDATA, 'MailPilot')
const defaults = {
  ...require('../engine/preferences.json'),
  indexDir: path.join(home, 'Index'),
  chatDir: path.join(home, 'Chatbox'),
}
const file = path.join(home, 'settings.json')
const choices = {
  source: ['classic', 'graph'],
  mode: ['subject', 'subject_body', 'all', 'attachment', 'sender', 'full'],
  storeScope: ['default', 'all'],
  theme: ['system', 'light', 'paper', 'dark'],
  palette: ['jade', 'ocean', 'graphite'],
  density: ['compact', 'comfortable', 'spacious'],
  dockSide: ['left', 'right'],
  searchLayout: ['window', 'sidebar'],
  aiLayout: ['window', 'sidebar'],
  readerFormat: ['original', 'plain'],
  readerLayout: ['pane', 'window'],
  defaultSort: ['date-desc', 'date-asc', 'sender-asc', 'sender-desc', 'subject-asc', 'subject-desc'],
}
const limits = {
  limit: [1, 1000],
  debounceMs: [100, 2000],
  cacheMiB: [1, 64],
  batchSize: [8, 256],
  pauseMs: [0, 1000],
  timeoutMs: [5, 500],
  refreshMinutes: [1, 1440],
  dockWidth: [300, 800],
  readerSize: [11, 26],
  readerZoom: [70, 180],
}
function read() {
  return fs.existsSync(file)
    ? { ...defaults, ...JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')) }
    : { ...defaults }
}
// The desktop single-instance process is the sole settings writer, also for Chatbox mode switches.
function save(patch) {
  const next = read()
  for (const [key, input] of Object.entries(patch)) {
    if (!Object.hasOwn(defaults, key)) throw Error('未知设置项')
    let value = input
    if (choices[key] && !choices[key].includes(value)) throw Error('选项无效')
    if (limits[key] && (!Number.isInteger(value) || value < limits[key][0] || value > limits[key][1]))
      throw Error('数值超出范围')
    if (typeof defaults[key] !== typeof value) throw Error('设置值类型不正确')
    if (key.endsWith('Color') && !(key !== 'highlightColor' && value === '') && !/^#[\da-f]{6}$/i.test(value))
      throw Error('请选择有效的颜色')
    if (key === 'readerFont' && (!value.trim() || value.length > 80 || /[<>{};]/.test(value)))
      throw Error('字体名称无效')
    if (key === 'clientId') {
      value = value.trim().toLowerCase()
      if (value && !/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/.test(value))
        throw Error('Microsoft 应用 ID 格式不正确')
    }
    if (key === 'indexDir' || key === 'chatDir') {
      value = value.trim().replace(/%([^%]+)%/g, (m, k) => process.env[k] || m)
      if (!/^[a-z]:[\\/]/i.test(value)) throw Error('请选择本地磁盘上的绝对目录')
      value = path.resolve(value)
      fs.mkdirSync(value, { recursive: true })
      fs.accessSync(value, fs.constants.W_OK)
    }
    next[key] = value
  }
  fs.mkdirSync(home, { recursive: true })
  const temp = file + '.' + randomUUID() + '.tmp'
  try {
    fs.writeFileSync(temp, JSON.stringify(next, null, 2))
    fs.renameSync(temp, file)
  } finally {
    fs.rmSync(temp, { force: true })
  }
  return next
}
module.exports = { root, home, defaults, read, save }
