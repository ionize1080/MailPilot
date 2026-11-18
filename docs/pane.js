'use strict'
const launch = document.getElementById('launch')
if (launch) {
  const actions = { search: '正则查找邮件', ai: '打开 AI 助手', settings: '设置与邮箱连接' }
  const requested = new URLSearchParams(location.search).get('action')
  const action = Object.hasOwn(actions, requested) ? requested : 'search'
  launch.href = 'mailpilot://' + action
  launch.textContent = actions[action]
} else if (window.Office) {
  Office.onReady(() => {
    for (const link of document.querySelectorAll('nav a')) link.addEventListener('click', event => {
      if (Office.context.ui && typeof Office.context.ui.openBrowserWindow === 'function') {
        try { Office.context.ui.openBrowserWindow(link.href); event.preventDefault() } catch { /* Use the ordinary link. */ }
      }
    })
  })
}
