# MailPilot

MailPilot 为 Windows 上的 Outlook 提供本地正则邮件查找和基于 Chatbox Community Edition 1.20.3 的 AI 助手。桌面包适用于 64 位 Windows，经典 Outlook 可为 32 或 64 位。

## 开始使用

1. 从 [GitHub Releases](https://github.com/ionize1080/MailPilot/releases/latest) 下载 Windows ZIP，解压整个 MailPilot 文件夹到固定位置。
2. 关闭经典 Outlook，双击 MailPilot.exe，按默认的“当前用户”点“启用此目录”，再启动 Outlook。在功能区的 **MailPilot** 选项卡打开“正则查找”。使用整机部署的电脑请按下方“Outlook 2010 与整台电脑部署”操作。
3. 首次打开查找会索引默认邮箱。可一边建索引一边查找，窗口底部显示已索引封数。在“设置 → 邮箱与索引”中可切换到所有已挂载邮箱与 PST。
4. 输入正则，例如用“标题”查 `PO-\d{6}`，用“发件人”查 `@example\.org`，用“附件名”查 `季度.*\.xlsx$`。单击结果即可在右侧阅读邮件（Esc 清空表达式，/ 聚焦输入框，下拉可选最近用过的表达式，滚动到底自动加载更多），用 F3 定位下一处命中，或点“在 Outlook 中打开”进入原件。
5. 打开“AI 助手”，在 Chatbox 设置中选择支持工具调用的模型并填写自己的 API 密钥。例如可以问“用附件名正则查找 Aurora 开头的 PDF，再读取命中邮件的正文”。服务还提供索引状态、文件夹计数和分段读取。

## 窗口与阅读

正则查找、邮件阅读窗和设置使用 Electron。查找与 AI 助手各有独立的窗口偏好，可用窗口右上方的侧栏按钮切换，保留当前表达式、结果和对话。经典 Outlook 将侧栏放在当前窗口的任务窗格里。新版 Outlook 使用跟随邮件窗口的贴边侧栏。单独启动时可以贴靠桌面边缘。升级后请在解压目录运行 Enable.cmd，并重新启动经典 Outlook，以注册侧栏。

独立查找窗口默认左边列出结果、右边显示详情。拖动分隔线可调整宽度，双击恢复默认。在列表中可用上下方向键连续阅读。要使用独立阅读窗，进入 **设置 → 窗口与侧栏 → 邮件详情**。查找停靠到侧边栏后，单击结果始终打开独立阅读窗。

结果上方的“排序”提供收件日期、发件人、主题各自的升降序。日期默认最新在前。发件人和主题按中文拼音、字母和数字顺序排列，同名时优先显示较新的邮件。整个命中集合使用同一顺序分页，可在 **设置 → 查找偏好 → 默认排序** 中更改启动时的选择。

| 查找范围 | 匹配字段 |
| --- | --- |
| 标题 | 邮件主题 |
| 标题与正文 | 主题、正文 |
| 内容与附件 | 主题、正文、附件文件名。沿用旧版相同范围。 |
| 附件名 | 各个附件的文件名 |
| 发件人 | 发件人和实际代发人的姓名、地址 |
| 全文 | 上述字段，另含收件人、抄送、可见密送、回复地址、收发时间、类别、文件夹、邮件头、链接及其他可读取的属性 |

详情使用完整的索引快照。HTML 邮件保留原文样式、表格、引用和内嵌图片，纯文本保留换行。可展开属性与 Internet 邮件头，并用 F3 或 Shift+F3 前后定位。外部图片可在阅读该封邮件时手动加载。经典 Outlook 的 Word 专用排版与 Chromium 存在差异，可通过原件核对。附件名参与匹配，附件文件内容不属于邮件正文字段。

### 附件

单击附件卡片可以预览，右键或点卡片上的“…”可以下载或复制单个附件。**下载全部**只需选择一次文件夹，有同名文件时自动编号。**复制全部**会把实际文件放入 Windows 剪贴板，可直接粘贴到资源管理器或新邮件。关闭 MailPilot 后仍可粘贴。

预览中可切换同封邮件的附件，按 Esc 返回原邮件。PDF、Word 和 PowerPoint 支持分页，Excel 支持切换工作表，Markdown 显示标题和表格，图片可缩放。支持 DOCX、XLSX、PPTX 及常见旧版 DOC、XLS、PPT，也支持 CSV、TSV、TXT、PNG、JPEG、GIF、WebP、BMP 和 AVIF。部分旧文档使用内容预览呈现文字和表格。文件按需从经典 Outlook 或 Microsoft Graph 取得，在本机渲染。云端链接附件可在 Outlook 原件中打开。

单个文件的内置预览上限为 96 MiB，文本预览最多读取前 512 KiB，下载和复制可取得完整原件。预览临时文件随桌面进程退出清理。可粘贴的文件暂存在本用户 MailPilot 数据目录的 AttachmentClipboard 内，之后复制附件时会清理超过七天的旧批次。

## 设置和部署

| 设置 | 作用 |
| --- | --- |
| 本地索引目录 | 可使用当前用户可写的本地磁盘目录。切到空目录会重新索引，切回旧目录可复用旧索引。 |
| 外观 | 跟随系统、薄荷浅色、暖纸、墨蓝深色。翡翠、海蓝、石墨三套图标与界面配色，支持自选强调色、选中背景和匹配高亮。可为 AI 助手单独切换主题同步。[PagePilot 配色参考](https://github.com/ionize1080/PagePilot/blob/main/chatbox/settings.html) |
| 阅读和列表 | 原始格式或纯文本、原文缩放、纯文本字体与字号、属性展开、高亮、列表密度、片段和文件夹路径。 |
| 窗口 | 查找和助手各自的显示方式、邮件详情的位置、侧栏宽度及左右位置。 |
| 邮箱与查找 | 默认邮箱或所有已打开的邮箱与 PST、文件夹过滤、六种查找范围、大小写和每页数量。 |
| 性能 | 输入防抖、正则匹配时限、SQLite 缓存、每批邮件数、批间休息、自动刷新开关及间隔。 |
| AI 助手 | Chatbox 数据目录可选。供应商、模型和会话使用 Chatbox 自带设置。 |
| 新版 Outlook | 可选 Microsoft Graph 邮箱连接，使用独立索引。 |

默认设置及索引位于 `%LOCALAPPDATA%\MailPilot`。Chatbox 设置和对话默认存放于其 Chatbox 子目录。升级时保留原设置、邮件 ID 和旧索引内容，下一次刷新补齐信头和富文本。手动关闭自动刷新时可点“刷新索引”。经典 Outlook 中已移动或移除的邮件在成功刷新后对账。遇到单封读取失败会显示数量，保留上次可读记录。

部署器在选定范围注册 MailPilot 的 Outlook 加载项、两个专属 COM 类和 mailpilot 链接。更新时可将新版解压到新目录，再启用该目录。移动或移除程序前，请在原目录选择原部署范围，点“停用此目录”。Enable.cmd 和 Disable.cmd 使用当前用户范围。个人设置和索引存放在独立的数据目录。

### Outlook 2010 与整台电脑部署

如果 PagePilot 在这台电脑上使用“整台电脑（管理员环境）”，MailPilot 可使用相同的部署范围。以下操作都能在图形界面完成。

1. 退出 Outlook。将完整 ZIP 解压到固定的、由管理员维护的本地目录，例如 `C:\Program Files\MailPilot`。其他账户的 Outlook 也会从这里加载程序。
2. 右键新目录里的 **MailPilot.exe → 以管理员身份运行**。选择 **整台电脑（需管理员权限）**，点 **启用此目录**。成功后，管理器会移除运行部署器的账户中可能遮蔽整机版本的旧 MailPilot 注册。若使用了另一个管理员账户，请先用原账户在原目录停用旧的当前用户版本。
3. 按平时的方式启动 Outlook，打开收件箱。在 MailPilot.exe 中点 **检查实际加载**。看到 **已连接此目录，功能区已加载（已验证）**，即可使用 MailPilot 选项卡。

“启动设置 LoadBehavior=3”表示已配置随 Outlook 启动。COM 加载项窗口显示的 mscoree.dll 是 .NET 加载入口。若仍显示“未加载”，请保持 Outlook 开着，点“复制检查结果”取得 Outlook 版本、位数、两个范围的注册信息和最近一次可用的连接错误。连接和功能区回执按 Windows 会话保存在当前用户的本地 MailPilot 数据中。

## 两种 Outlook

**经典 Outlook** 使用 .NET Framework 4.8 的轻量 COM 功能区，通过 Outlook 2010 已有的邮件表及晚绑定对象接口读取本机存储。目标为 64 位 Windows 10 21H1 上的 Outlook 2010，以及后续经典版。本机实际验证的 Office 版本和性能数据见 [验证记录](TESTING.md)。

**新版 Outlook for Windows** 使用随包的 web/MailPilot.xml。先在 Windows 启用便携包，打开 [Outlook 加载项管理](https://aka.ms/olksideload)，在“我的加载项 → 自定义加载项 → 从文件添加”选择该清单。在邮件阅读界面打开 MailPilot，使用浏览器按钮启动本机查找或助手。组织须允许加载自定义加载项。静态任务窗格位于 GitHub Pages，以 HTTPS 提供入口。

新版整箱索引面向 Microsoft 365 和 Outlook.com 邮箱。先在 Microsoft Entra 中注册支持相应帐户类型的多租户公共客户端，启用“允许公共客户端流”，添加 Microsoft Graph 的委托 Mail.Read。将应用 ID 填入“邮箱与索引”，点“连接 Microsoft 邮箱”，在 Microsoft 登录页完成设备代码授权。登录后点击“刷新索引”。刷新凭据受 Windows 当前用户 DPAPI 保护。第三方 IMAP/PST 邮箱可从经典 Outlook 接入。[Microsoft 的新版 Outlook 加载项说明](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/one-outlook) · [邮件 delta 接口](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0)

## 查找原理

第一次同步按文件夹、按批建立 SQLite FTS5 三字符倒排索引，正文按需压缩。两个常用汉字也可进入倒排索引。经典版后续刷新先批量比较邮件标识及版本，Graph 按文件夹保存 delta 游标。索引和查询分别使用连接，WAL 允许在刷新期间读取已提交的数据。没有邮件索引常驻服务，关闭查找和 AI 窗口后工作进程退出。

查询会从可安全分析的表达式提取必需字面量，先筛候选，再用 regex VERSION0 对选定原始字段逐项验证。复杂扩展表达式回退到流式扫描。日期、发件人和主题的排序键保存在本地索引中。详情高亮也使用同一正则引擎。查询支持取消，匹配超时会明确提示结果不完整。

## AI 和数据流

桌面界面从本地文件加载。窗口控制使用 Electron IPC 与 Windows COM，邮件查询进程和内置 MCP 工具均使用标准输入输出（stdio），启动时无需开放本地监听端口。

Chatbox 由上游 v1.20.3 固定提交 d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb 的 TypeScript 源码编译。补丁及构建步骤随源码发布。MailPilot 内置的四个只读 MCP 工具通过本机 stdio 连接，名称为 search_mail、read_mail、list_folders 和 index_status。AI 请求使用上游供应商 SDK 和原请求适配器，保留直连、代理及供应商专属请求头。邮件搜索本身在本机执行。使用 AI 时，聊天提示和模型调用工具取得的邮件片段会发给所选供应商。索引文件含本地邮件数据，应存放在本人控制的目录。

## 构建

在 64 位 Windows 上准备 Python 3.12、Git、Node/npm、.NET Framework 4.8 和 Office PIA / Extensibility 编译引用，运行根目录 build.ps1。脚本从固定提交构建 Chatbox，校验并打包 Windows 运行组件。最终 ZIP 和 SHA-256 位于 dist。Windows 桌面使用者只需解压发布包。源码采用 GPL-3.0，第三方说明见 [THIRD-PARTY.md](THIRD-PARTY.md)。
