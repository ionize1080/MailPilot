/* Drive the compiled Chatbox input box with an isolated synthetic Outlook index.
   Key injection is in memory and test-only. Record header names and outcomes, never credentials. */
'use strict'
const fs = require('node:fs')
const path = require('node:path')
const { app, BrowserWindow, ipcMain, session } = require('electron')
const root = path.resolve(__dirname, '..')
const out = path.join(root, '.build')
const home = process.env.MAILPILOT_HOME
if (!home || !path.resolve(home).startsWith(out + path.sep)) throw Error('An isolated fixture profile is required')
const model = process.env.MAILPILOT_QA_MODEL || 'qwen3.7-plus'
const host = process.env.MAILPILOT_QA_HOST || 'https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
if (!['token-plan.cn-beijing.maas.aliyuncs.com','coding.dashscope.aliyuncs.com','coding-intl.dashscope.aliyuncs.com'].includes(new URL(host).hostname)) throw Error('Unexpected test endpoint')
const key = fs.readFileSync(process.env.MAILPILOT_QA_KEY_FILE, 'utf8').replace(/^\uFEFF/,'').trim()
const record = {model, host, requests: [], tools: [], ready:false, answerVerified:false}
const original = ipcMain.handle.bind(ipcMain)
function configured(saved = {}) {
  return {...saved, defaultChatModel: { provider:'openai', model }, threadNamingModel:{ provider:'openai', model },
    providers: {openai:{apiHost:host,apiKey:key,models:[{modelId:model,capabilities:['tool_use'],contextWindow:65536}]}},
    language:'zh-Hans', autoUpdate:false}
}
ipcMain.handle = (channel, handler) => {
  if (channel === 'getStoreValue') return original(channel, async(e,name,...a) => {
    const v = await handler(e,name,...a)
    return name === 'settings' ? configured(v) : v
  })
  if (channel === 'getSettings') return original(channel, async(...a)=>configured(await handler(...a)))
  if (channel === 'setStoreValue') return original(channel,(e,name,json)=>handler(e,name,json.replaceAll(key,'')))
  if (channel === 'shouldShowAboutDialogWhenStartUp') return original(channel,()=>false)
  if (channel === 'mcp:stdio-transport:send') return original(channel,(e,id,msg)=>{
    if (msg.method === 'tools/call') record.tools.push(msg.params.name)
    return handler(e,id,msg)
  })
  return original(channel,handler)
}
const report = () => fs.writeFileSync(path.join(out,'live-result.json'),JSON.stringify(record,null,2))
app.whenReady().then(()=>{
  session.defaultSession.webRequest.onBeforeRequest({urls:[new URL(host).origin+'/*']},(d,cb)=>{
    const bytes=(d.uploadData||[]).filter(x=>x.bytes).map(x=>x.bytes)
    if(bytes.length) {
      const body=JSON.parse(Buffer.concat(bytes))
      record.payloads ||= []
      record.payloads.push({model:body.model,tools:body.tools?.map(t=>t.function?.name),roles:body.messages?.map(m=>m.role),
        promptPresent:JSON.stringify(body.messages).includes('Aurora-QA')})
    }
    cb({})
  })
  session.defaultSession.webRequest.onBeforeSendHeaders({urls:[new URL(host).origin+'/*']},(d,cb)=>{
    const h=Object.fromEntries(Object.entries(d.requestHeaders).map(([k,v])=>[k.toLowerCase(),v]))
    record.requests.push({method:d.method, path:new URL(d.url).pathname, userAgent:h['user-agent'],
      bearerMatches:h.authorization==='Bearer '+key, contentType:h['content-type'],
      chatboxProxyHeader:!!h['chatbox-target-uri']})
    report();cb({requestHeaders:d.requestHeaders})
  })
  session.defaultSession.webRequest.onCompleted({urls:[new URL(host).origin+'/*']},d=>{
    record.lastHTTP=d.statusCode;report()
  })
})
require(path.join(root,'dist/MailPilot/Chatbox/bootstrap.cjs'))
const delay=ms=>new Promise(r=>setTimeout(r,ms))
async function until(fn,n,label){
  for(let i=0;i<n;i++){const value=await fn();if(value)return value;await delay(500)}
  throw Error('Timeout: '+label)
}
;(async()=>{
  let win = await until(()=>BrowserWindow.getAllWindows()[0],100,'window')
  const js = s=>win.webContents.executeJavaScript(s,true)
  await until(async()=>!win.webContents.isLoading() && await js("!!document.querySelector('#message-input, [data-testid=message-input]')"),150,'Chatbox input')
  record.ready=true;report()
  await delay(2200)
  await js("document.querySelector('#message-input, [data-testid=message-input]').focus()")
  await win.webContents.insertText('这是合成邮件的集成测试。请实际调用 MailPilot 的 search_mail 工具，mode 选 attachment，用正则 Aurora-QA-[0-9]+ 搜索附件名。再用 read_mail 读取命中邮件，回复正文中 Proof code 后的验证代码。不要猜测。')
  await until(()=>js("document.querySelector('#message-input').value.includes('Aurora-QA')"),15,'input value')
  await delay(650)
  win.webContents.sendInputEvent({type:'keyDown',keyCode:'Enter'})
  win.webContents.sendInputEvent({type:'keyUp',keyCode:'Enter'})
  await until(async()=>record.tools.includes('search_mail') && record.tools.includes('read_mail') &&
    await js("document.body.innerText.includes('JADE-8317')"),360,'model answer and both real MCP calls')
  if(!record.requests.some(r=>r.bearerMatches && r.contentType?.includes('application/json')))throw Error('Provider headers differ')
  record.answerVerified=true;report();app.exit(0)
})().catch(async e=>{
  record.error=String(e.message).replaceAll(key,'[redacted]')
  const win=BrowserWindow.getAllWindows()[0]
  if(win) record.screen=(await win.webContents.executeJavaScript('document.body.innerText.slice(-1600)').catch(()=>'' )).replaceAll(key,'[redacted]')
  report();app.exit(1)
})
