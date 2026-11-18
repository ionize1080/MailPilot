# MailPilot

MailPilot 为 Windows 上的 Outlook 提供本地正则邮件查找和基于 Chatbox Community Edition 1.20.3 的 AI 助手。桌面包适用于 64 位 Windows，经典 Outlook 可为 32 或 64 位。

## 开始使用

1. 从 [GitHub Releases](https://github.com/ionize1080/MailPilot/releases/latest) 下载 Windows ZIP，解压整个 MailPilot 文件夹到固定位置。
2. 关闭经典 Outlook，双击 MailPilot.exe，点“启用此目录”，再启动 Outlook。在功能区的 **MailPilot** 选项卡打开“正则查找”。也可运行 Enable.cmd。
3. 首次打开查找会索引默认邮箱。可一边建索引一边查找，窗口底部显示已索引封数。在“设置 → 索引与资源”中可切换到所有已挂载邮箱与 PST。
4. 输入正则，例如用仅标题模式查找 `PO-\d{6}`，用标题和正文模式查找 `预算.{0,20}调整`，用仅附件名模式查找 `季度.*\.xlsx$`。查找按字段分别匹配，附件逐个文件名匹配。双击结果打开原邮件。
5. 打开“AI 助手”，在 Chatbox 设置中选择支持工具调用的模型并填写自己的 API 密钥。例如可以问“用附件名正则查找 Aurora 开头的 PDF，再读取命中邮件的正文”。服务还提供索引状态、文件夹计数和分段读取。

## 设置和部署

| 设置 | 作用 |
| --- | --- |
| 本地索引目录 | 可使用当前用户可写的本地磁盘目录。切到空目录会重新索引，切回旧目录可复用旧索引。 |
| 邮箱与查找 | 默认邮箱或所有已打开的邮件存储区、结果窗口内的文件夹过滤、四种字段模式、大小写、每页数量。 |
| 性能 | 输入防抖、正则匹配时限、SQLite 缓存、每批邮件数、批间休息、自动刷新开关及间隔。 |
| AI 助手 | Chatbox 数据目录可选。供应商、模型和会话使用 Chatbox 自带设置。 |
| 新版 Outlook | 可选 Microsoft Graph 邮箱连接，使用独立索引。 |

默认设置及索引位于 `%LOCALAPPDATA%\MailPilot`。Chatbox 设置和对话默认存放于其 Chatbox 子目录。每次查找读取本地索引，显示上次刷新的邮件内容。经典 Outlook 中已移动或移除的邮件在成功刷新后对账。遇到单封读取失败会显示数量，保留上次可读记录。

启用只写当前用户的 Outlook 加载项、COM 类及 MailPilot URL 注册信息。部署器采用与 PagePilot 类似的解压、启用、停用方式，系统软件卸载列表不会新增条目。移动目录之前运行 Disable.cmd，在新目录重新启用。更新时也可以直接启用新版本，旧版本的停用命令会核对归属。需要彻底移除时，先停用并关闭 MailPilot，再按需删除解压目录、索引和个人设置。

## 两种 Outlook

**经典 Outlook** 使用 .NET Framework 4.8 的轻量 COM 功能区，通过 Outlook 2010 已有的邮件表及晚绑定对象接口读取本机存储。目标为 64 位 Windows 10 21H1 上的 Outlook 2010，以及后续经典版。本机实际验证的 Office 版本和性能数据见 [验证记录](TESTING.md)。

**新版 Outlook for Windows** 使用随包的 web/MailPilot.xml。先在 Windows 启用便携包，打开 [Outlook 加载项管理](https://aka.ms/olksideload)，在“我的加载项 → 自定义加载项 → 从文件添加”选择该清单。在邮件阅读界面打开 MailPilot，使用浏览器按钮启动本机查找或助手。组织须允许加载自定义加载项。静态任务窗格位于 GitHub Pages，以 HTTPS 提供入口。

新版整箱索引面向 Microsoft 365 和 Outlook.com 邮箱。先在 Microsoft Entra 中注册支持相应帐户类型的多租户公共客户端，启用“允许公共客户端流”，添加 Microsoft Graph 的委托 Mail.Read。将应用 ID 填入“AI 与邮箱”，点“连接 Microsoft 邮箱”，在 Microsoft 登录页完成设备代码授权。登录后点击“刷新索引”。刷新凭据受 Windows 当前用户 DPAPI 保护。第三方 IMAP/PST 邮箱可从经典 Outlook 接入。[Microsoft 的新版 Outlook 加载项说明](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/one-outlook) · [邮件 delta 接口](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0)

## 查找原理

第一次同步按文件夹、按批建立 SQLite FTS5 三字符倒排索引，正文按需压缩。两个常用汉字也可进入倒排索引。经典版后续刷新先批量比较邮件标识及版本，Graph 按文件夹保存 delta 游标。索引和查询分别使用连接，WAL 允许在刷新期间读取已提交的数据。没有邮件索引常驻服务，关闭查找和 AI 窗口后工作进程退出。

查询会从可安全分析的表达式提取必需字面量，先筛候选，再用 regex VERSION0 对选定原始字段逐项验证。复杂扩展表达式回退到流式扫描。结果按收件时间倒序分页。查询支持取消，匹配超时会明确提示结果不完整。索引存放可查找的正文和附件名。附件内容不参与匹配。

## AI 和数据流

Chatbox 由上游 v1.20.3 固定提交 d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb 的 TypeScript 源码编译。补丁及构建步骤随源码发布。MailPilot 内置的四个只读 MCP 工具通过本机 stdio 连接，名称为 search_mail、read_mail、list_folders 和 index_status。AI 请求使用上游供应商 SDK 和原请求适配器，保留直连、代理及供应商专属请求头。邮件搜索本身在本机执行。使用 AI 时，聊天提示和模型调用工具取得的邮件片段会发给所选供应商。索引文件含本地邮件数据，应存放在本人控制的目录。

## 构建

在 64 位 Windows 上准备 Python 3.12、Git、Node/npm、.NET Framework 4.8 和 Office PIA / Extensibility 编译引用，运行根目录 build.ps1。脚本从固定提交构建 Chatbox，校验并打包 Windows 运行组件。最终 ZIP 和 SHA-256 位于 dist。Windows 桌面使用者只需解压发布包。源码采用 GPL-3.0，第三方说明见 [THIRD-PARTY.md](THIRD-PARTY.md)。
