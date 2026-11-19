import init, { WasmDocument } from './node_modules/office-oxide-wasm/web/office_oxide.js'

self.onmessage = async ({ data }) => {
  let doc
  try {
    await init()
    doc = new WasmDocument(new Uint8Array(data.bytes), data.format)
    const html = doc.toHtml()
    if (html.length > 2 * 1024 * 1024) {
      const text = doc.plainText()
      self.postMessage({ text: text.slice(0, 512 * 1024), partial: text.length > 512 * 1024 })
    } else self.postMessage({ html })
  } catch (e) {
    self.postMessage({ error: String(e) })
  } finally {
    doc?.free()
  }
}
