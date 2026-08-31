## 无需 Python，完整解压后即可使用

本版本提供 Windows、macOS 和 Linux 原生发布包。普通用户请下载与自己系统匹配的 ZIP，不要下载 GitHub 自动附带的 Source code 压缩包。

## v3.6.3 更新说明

1. 完成 Issue #9 的自动重登录 Cookie 收尾：登录 POST 只携带本轮验证码下发的 `route` 与 `insert_cookie`，不再拼接内存中已经过期的 `route`、`JSESSIONID` 等学校会话 Cookie。
2. 验证码 token、图片和登录提交形成同一轮干净 Cookie 契约，避免重复 Cookie 名让学校端读取到旧值；手动首登和 OCR 自动重登使用相同规则。
3. 验证码接口连续第 3 次返回缺失必要 Cookie、畸形 token 等结构性异常时会提前停止并给出明确提示；取得一次完整响应立即清零计数，普通 OCR 识别失败仍可使用最多 50 张验证码的预算。
4. WebVPN 请求显式省略学校会话 Cookie 时仍保留独立的网关认证 Cookie；主站请求继续完全省略 Cookie，自动选课提交固定使用学校主站。
5. 审查、补强并合入 PR #12，新增登录请求头、空 Cookie、省略语义、WebVPN 网关 Cookie 和连续异常重置等回归测试。
6. 保留 v3.6.2 的验证码 token/图片无 Cookie 获取规则，学校可以为每轮验证码重新下发有效的 `route` 与 `insert_cookie`。
7. 保留 Linux 打包版外部子进程环境净化：正确识别 Nuitka 编译态，并过滤 OpenCV 导入产生的空库路径和发布目录条目，避免捆绑 OpenSSL 遮蔽系统库。
8. Linux 浏览器入口继续使用无 shell 的 `xdg-open`，失败时回退 `gio open`；WebVPN 受控浏览器使用相同隔离环境，Windows 与 macOS 行为不变。
9. “学校原始页面”保持为浏览器真实链接；Linux Release 构建继续验证真实产物的子进程环境以及 ddddocr、OpenCV 与 ONNX Runtime 初始化。
10. 爆发和一般模式的业务失败阈值均可填写 1 至 1,000,000 次或设为“无限次”，网络异常和学校 5xx 不计入业务失败。
11. 单门课程连续未知响应的保护性暂停阈值保持为 2000 次；中间收到一次可识别响应即清零，网络异常、阶段门控和会话恢复使用独立保护。
12. 保留任务暂停后增删、重试、开关与优先级调整、安全停止、课表、学分统计、多校区目录和账号隔离缓存。
13. OCR 自动重登录兼容 `ddddocr 1.6.1` 多种 API；CI 覆盖 Python 3.13/3.14，各平台构建前均真实初始化 OCR。
14. Release 运行数据继续位于系统用户目录，升级后沿用原有清单、Card Key 身份和安全课程缓存。
15. 学校密码只保存在当前进程内存中；WebVPN 只用于认证后的只读查询，本版不提供自动退课。
16. 自动测试全部使用假数据，不访问学校，也不执行选课或退课操作。
17. Release 只提供各平台与源码 ZIP，不附带独立 `.sha256` 或 `SHA256SUMS.txt` 文件。

| 系统 | 下载文件 | 启动方式 |
| --- | --- | --- |
| Windows 10/11 64 位 | `SZU-Course-Help-v3.6.3-windows-x64.zip` | 双击 `启动抢课助手.bat` |
| Apple 芯片 Mac | `SZU-Course-Help-v3.6.3-macos-arm64.zip` | 双击 `启动抢课助手.command` |
| Intel 芯片 Mac | `SZU-Course-Help-v3.6.3-macos-x64.zip` | 双击 `启动抢课助手.command` |
| Linux 64 位 | `SZU-Course-Help-v3.6.3-linux-x64.zip` | 运行 `启动抢课助手.sh` |

每个发布包均含可执行程序、平台启动脚本、`使用手册.md`、`使用手册.pdf`、`更新记录.md`、项目说明和许可证。`SZU-Course-Help-v3.6.3-source.zip` 供开发者使用。

## 首次运行

1. 完整解压 ZIP，不要在压缩包预览窗口内直接运行，也不要只拖出主程序。
2. 运行平台启动脚本，在终端输入学号并生成本机 Card Key。
3. 输入 `Y` 后，程序会启动本地网页并打开登录页。
4. 首次登录由用户输入学校密码并手动完成点击验证码。
5. 预选、未开放、已结束和未知阶段禁止启动自动选课；只有学校返回明确允许的复选、正选、补选或补退选批次才可在二次确认后启动。

## 数据与安全

- Windows 数据目录：`%APPDATA%\SZU-Course-Help\`。
- macOS 数据目录：`~/Library/Application Support/SZU-Course-Help/`。
- Linux 数据目录：`${XDG_DATA_HOME:-~/.local/share}/SZU-Course-Help/`。
- 学校密码、token 与 Cookie 不写入磁盘；关闭程序后必须重新手动登录。
- 当前版本未购买 Windows 或 Apple 商业代码签名证书，SmartScreen 或 Gatekeeper 可能显示未知开发者提示。
- 只从本仓库官方 Release 下载，不要运行群文件、网盘或陌生链接中的副本。
- 学校接口和规则可能变化，关键选课结果以学校官方系统为准。

完整步骤、任务暂停编辑、数据迁移、自动重登录和常见问题请阅读发布包中的 `使用手册.pdf`。
