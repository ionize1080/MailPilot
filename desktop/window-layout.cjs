'use strict'
const { screen } = require('electron')
const { execFile, spawn } = require('node:child_process')
const { createInterface } = require('node:readline')
const path = require('node:path')
const { root } = require('./preferences.cjs')
const python = path.join(root, 'Runtime', 'python.exe')
const script = path.join(root, 'engine', 'pane.py')

function pane(action, kind, handle, side, width) {
  return new Promise((resolve) =>
    execFile(
      python,
      ['-B', script, action, kind, handle, side, String(width)],
      { windowsHide: true, timeout: 6000 },
      (error) => resolve(!error)
    )
  )
}
function within(bounds, area) {
  const width = Math.min(bounds.width, area.width),
    height = Math.min(bounds.height, area.height)
  return {
    width,
    height,
    x: Math.max(area.x, Math.min(bounds.x, area.x + area.width - width)),
    y: Math.max(area.y, Math.min(bounds.y, area.y + area.height - height)),
  }
}
class WindowLayout {
  constructor(win, kind, source, onChange) {
    Object.assign(this, { win, kind, source, onChange, mode: 'window', queue: Promise.resolve() })
    const handle = win.getNativeWindowHandle()
    this.handle = (handle.length === 8 ? handle.readBigUInt64LE() : handle.readUInt32LE()).toString()
    this.minimum = win.getMinimumSize()
    win.hookWindowMessage(0x802a, () => {
      if (this.mode === 'outlook' && this.config) {
        this.mode = 'edge' // The native host already released its ownership.
        this.apply({ ...this.config, [kind + 'Layout']: 'window' }, true)
      }
    })
    this.reposition = () => this.position()
    screen.on('display-metrics-changed', this.reposition)
    screen.on('display-removed', this.reposition)
    win.on('closed', () => {
      this.stopTracking()
      screen.removeListener('display-metrics-changed', this.reposition)
      screen.removeListener('display-removed', this.reposition)
    })
  }
  apply(cfg, reveal = false) {
    const operation = () => this.update(cfg, reveal)
    this.queue = this.queue.then(operation, operation)
    return this.queue
  }
  async update(cfg, reveal) {
    this.config = cfg
    const win = this.win
    if (win.isDestroyed()) return
    const requested = cfg[this.kind + 'Layout'],
      side = cfg.dockSide,
      width = cfg.dockWidth
    const same = this.side === side && this.width === width
    this.side = side
    this.width = width
    if (requested === 'window') {
      if (this.mode !== 'window') {
        this.stopTracking()
        if (this.mode === 'outlook') await pane('detach', this.kind, this.handle, side, width)
        if (win.isDestroyed()) return
        win.setResizable(true)
        win.setMinimumSize(...this.minimum)
        win.setSkipTaskbar(false)
        const previous = this.floating
        if (previous) win.setBounds(within(previous, screen.getDisplayMatching(previous).workArea))
        if (this.maximized) win.maximize()
        this.mode = 'window'
        reveal = true
      }
    } else if (this.mode === 'window' || !same || reveal) {
      if (this.mode === 'window') {
        this.maximized = win.isMaximized()
        this.floating = win.getNormalBounds()
        if (win.isMinimized()) win.restore()
        if (win.isMaximized()) win.unmaximize()
        win.setMinimumSize(260, 120)
      }
      this.stopTracking()
      const attached =
        this.source === 'classic' && (await pane('attach', this.kind, this.handle, side, width))
      if (win.isDestroyed()) return
      this.mode = attached ? 'outlook' : 'edge'
      win.setResizable(false)
      win.setSkipTaskbar(attached)
      if (!attached) {
        this.area = screen.getDisplayMatching(win.getBounds()).workArea
        this.position()
        this.trackOutlook()
      }
    }
    this.onChange(this.mode)
    if (reveal && !win.isDestroyed()) {
      if (win.isMinimized()) win.restore()
      win.show()
      win.focus()
    }
    return this.mode
  }
  position() {
    if (this.mode !== 'edge' || this.win.isDestroyed()) return
    const area = this.anchor || screen.getDisplayMatching(this.area || this.win.getBounds()).workArea
    const width = Math.min(this.width, area.width)
    const bounds = {
      x: this.side === 'left' ? area.x : area.x + area.width - width,
      y: area.y,
      width,
      height: area.height,
    }
    this.win.setBounds(bounds)
  }
  trackOutlook() {
    const child = spawn(python, ['-B', script, 'follow', this.source], {
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'ignore'],
    })
    this.tracker = child
    child.on('error', () => {})
    createInterface({ input: child.stdout }).on('line', (line) => {
      if (this.tracker !== child || this.win.isDestroyed()) return
      const state = JSON.parse(line)
      if (state === 'minimized') {
        this.win.hide()
        this.ownerHidden = true
        return
      }
      this.anchor =
        state &&
        within(
          screen.screenToDipRect(null, state.bounds),
          screen.getDisplayMatching(screen.screenToDipRect(null, state.bounds)).workArea
        )
      this.position()
      if (this.ownerHidden) {
        this.ownerHidden = false
        this.win.showInactive()
      }
      if (state?.active && !this.win.isMinimized()) this.win.moveTop()
    })
  }
  stopTracking() {
    if (this.tracker) this.tracker.kill()
    this.tracker = null
    this.anchor = null
    this.ownerHidden = false
  }
  async collapse() {
    if (this.mode === 'outlook') await pane('hide', this.kind, this.handle, this.side, this.width)
    else this.win.minimize()
  }
}
module.exports = { WindowLayout, pane }
