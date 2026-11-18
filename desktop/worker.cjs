'use strict'
const { spawn } = require('node:child_process')
const { createInterface } = require('node:readline')
const path = require('node:path')
const { root } = require('./preferences.cjs')

class MailWorker {
  constructor(source) {
    this.pending = new Map()
    this.sequence = 0
    this.child = spawn(
      path.join(root, 'Runtime', 'python.exe'),
      ['-B', path.join(root, 'engine', 'service.py'), '--ui'],
      {
        cwd: root,
        windowsHide: true,
        env: { ...process.env, MAILPILOT_SOURCE: source },
        stdio: ['pipe', 'pipe', 'ignore'],
      }
    )
    this.child.stdout.setEncoding('utf8')
    createInterface({ input: this.child.stdout, crlfDelay: Infinity }).on('line', (line) => {
      try {
        const packet = JSON.parse(line),
          pending = this.pending.get(packet.id)
        if (!pending) return
        this.pending.delete(packet.id)
        if (packet.error) pending.reject(Error(packet.error))
        else pending.resolve(packet.result)
      } catch (e) {
        this.fail(e)
      }
    })
    this.child.on('error', (error) => this.fail(error))
    this.child.stdin.on('error', (error) => this.fail(error))
    this.child.on('exit', () => this.fail(Error('邮件进程已退出，请重新打开查找')))
  }
  fail(error) {
    this.closed = true
    for (const request of this.pending.values()) request.reject(error)
    this.pending.clear()
  }
  call(method, params = {}) {
    if (this.closed) return Promise.reject(Error('邮件进程已关闭'))
    return new Promise((resolve, reject) => {
      const id = ++this.sequence
      this.pending.set(id, { resolve, reject })
      this.child.stdin.write(JSON.stringify({ id, method, params }) + '\n')
    })
  }
  close() {
    this.child.stdin.end()
    this.fail(Error('已切换邮箱索引'))
  }
}
module.exports = MailWorker
