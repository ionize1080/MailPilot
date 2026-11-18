# 第三方软件与源码

MailPilot 的集成代码以 GNU GPL v3 发布，完整文本见 LICENSE。

| 组件 | 来源及说明 |
| --- | --- |
| Chatbox Community Edition 1.20.3 | GPL-3.0。桌面主进程、预加载模块和渲染界面均从固定源码编译。发行页另附实际编译输入的源码 ZIP。[上游提交](https://github.com/chatboxai/chatbox/tree/d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb) |
| Electron 44.7.0 | 采用 PagePilot 参考部署使用的 Windows x64 宿主版本。MIT 及 Chromium 第三方许可保留于 Browser/LICENSE、Browser/LICENSES.chromium.html。[Electron](https://github.com/electron/electron/releases/tag/v44.7.0) |
| CPython 3.12.10 Windows embeddable | PSF 及随附第三方许可见 Runtime/LICENSE.txt。[CPython](https://www.python.org/downloads/release/python-31210/) |
| pywin32 311、regex 2025.11.3 | 原许可随模块保留于 Runtime/Lib/site-packages。二进制下载地址和 SHA-256 见 scripts/runtime-lock.json。[pywin32](https://github.com/mhammond/pywin32) · [regex](https://pypi.org/project/regex/2025.11.3/) |
| JavaScript 依赖 | Chatbox 使用上游 pnpm 锁。独立宿主的运行依赖锁在 chatbox/package-lock.json。发行包 licenses/npm/packages.json 列出依赖版本及对应许可文件，包含构建工具。 |
| Office.js | 新版 Outlook 任务窗格在运行时从 Microsoft 官方 CDN 加载。[Microsoft 文档](https://learn.microsoft.com/en-us/office/dev/add-ins/develop/referencing-the-javascript-api-for-office-library-from-its-cdn) |

## Chatbox 集成差异

源码准备脚本只对指定上游提交执行。公开版标签的锁文件残留未发布组件，脚本仅校正 importer，使解析版本和完整性校验沿用上游锁。公开源码缺少 GitHub Copilot 定义、供应商 OAuth 的 IPC 实现、商业版脚本工具和错误信息翻译器，对应入口已在构建时处理。API 密钥供应商及原 MCP 客户端仍走上游实现。邮件助手按窗口启动与退出，随 MailPilot 一起更新。宿主使用原产品名和版本，浏览器标记反映随包的 Electron 版本。

相关源码包括 [OpenAI 供应商](https://github.com/chatboxai/chatbox/blob/d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb/src/shared/providers/definitions/models/openai.ts)、[请求适配器](https://github.com/chatboxai/chatbox/blob/d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb/src/renderer/utils/request.ts)和 [Chatbox 服务请求](https://github.com/chatboxai/chatbox/blob/d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb/src/shared/request/request.ts)。
