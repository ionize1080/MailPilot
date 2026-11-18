# MailPilot 0.2.0 验证记录

## 测试环境与范围

Windows 11、经典 Outlook 16.0.20527 x64、发行包内置的 Electron 和 Python。在真实 Outlook Explorer 中，分别将正则查找和已启动的 Chatbox 停靠到 Office 自定义任务窗格，再恢复为独立窗口。另行验证了功能区从 onLoad 到打开 Electron 设置的回调。

Electron 界面测试使用独立设置和合成邮箱。验证了发件人地址、跨样式正文高亮、抄送和邮件头匹配、表格、CID 图片、主题同步、切换索引目录及重开设置。查找、阅读和助手使用发行包中同一套代码。通过 Chatbox 配置中的 stdio 命令执行 MCP 初始化、工具枚举、全文搜索及分字段读取。在查找、助手与 MCP 工作进程运行期间，Windows 进程树检查未发现 TCP 监听端口。

目标组合中的 Windows 10 21H1 与 Outlook 2010 尚待实机验收。Graph 测试使用模拟响应验证文件夹、消息 delta、HTML、收件人、邮件头、扩展属性、内嵌图片、附件分页和令牌过期恢复。另用独立 Graph 测试配置验证了桌面阅读与贴边窗口。真实 Microsoft 365 租户登录及新版 Outlook 客户端内侧载仍待验证。

## 50,000 封合成邮件

每封有各自的标识、日期、标题、金额和中英文段落，四分之一带附件名。纯文本正文共 55.4 MiB。以 8 MiB SQLite 缓存创建并关闭新版索引，耗时 38.87 秒，主数据库为 99.6 MiB，压测进程峰值工作集 36.0 MiB。计时包括生成合成记录。真实邮箱的富文本、内嵌图片和 Outlook 读取耗时取决于邮件内容。

下表为同一索引上的查询，首次查询后重复 15 次。耗时是搜索引擎计时，不含输入防抖、Windows 窗口绘制及网络。每条查询均与逐封扫描比对命中 ID 及顺序。

| 模式及正则 | 命中 | 核验候选 | 中位 ms | P95 ms | 强制扫描 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 标题 `PO-04999\d` | 10 | 11 | 1.6 | 2.0 | 231.9 |
| 标题与正文 `晨星计划\s+RAVEN-\d+` | 13 | 13 | 0.6 | 1.0 | 775.6 |
| 内容与附件 `季度汇总-0499\d{2}\.xlsx` | 25 | 643 | 17.2 | 20.3 | 1031.5 |
| 标题与正文 `晨星` | 13 | 13 | 0.8 | 0.9 | 868.7 |
| 标题 `(?<=PO-)04999\d` | 10 | 50,000 | 229.0 | 321.2 | 230.2 |

另有 360 组索引与全扫描对照覆盖六种查找范围、大小写、Unicode、中文和扩展正则。专项测试覆盖旧索引迁移、代理发件人、地址锚点、UTF-16 偏移、零宽匹配、分页、更新、删除对账和取消。

## Outlook 与 Qwen

在本机 Outlook 创建、索引并卸载独立测试 PST，验证 HTML 表格、RTF 导出、抄送、类别、正文与附件。首次刷新读取 3 封，连续刷新读取 0 封，一次正文修改后读取 1 封。

0.1.0 的供应商联调记录显示，Qwen qwen3.7-plus 经 HTTPS 响应 HTTP 200，调用 search_mail 和 read_mail 并返回测试邮件中保存的校验值。0.2.0 验证了本机 Chatbox 和 stdio 工具往返，未重新发起付费模型请求。

## 复核

运行 tests/desktop-ui.ps1 可检查查找、阅读、设置与侧栏。使用 -Source graph 验证 Graph 桌面入口，-Assistant 验证编译后的 Chatbox、主题及 stdio。启用本目录的加载项后，可用发行包 Runtime/python.exe 运行 tests/outlook-pane.py 复核两个工具在真实 Office 任务窗格中的切换。

运行 tests/regression.py 和 tests/bench.py 时使用发行包中的 Runtime/python.exe。bench.py 接受一个尚不存在的数据库文件名。将 MAILPILOT_HOME 设为源码目录下的 .build/qa-mailbox，在该目录的 settings.json 中设置 {"autoRefresh":false}，再运行 tests/outlook_live.py 建立合成测试索引。执行 tests/run-live.ps1 -KeyFile 个人密钥文件可通过独立 Chatbox 配置重复真实测试。可用 -Bundle 指向解压后的发行包。
