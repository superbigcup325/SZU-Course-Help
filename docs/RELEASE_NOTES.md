## 无需 Python，完整解压后即可使用

本版本提供 Windows、macOS 和 Linux 原生发布包。普通用户请下载与自己系统匹配的 ZIP，不要下载 GitHub 自动附带的 Source code 压缩包。

## v3.6.2 更新说明

1. 修复 v3.6.1 自动重新登录获取验证码时继承过期学校 Cookie 的回归。验证码 token 与图片请求现在完全省略 `Cookie` 请求头，让学校重新下发有效的 `route` 与 `insert_cookie`。
2. 无 Cookie 规则同时覆盖手动登录验证码、旧 OCR 路径和当前自动重登录路径；登录提交、课程查询、抢课请求和 WebVPN 的 Cookie 行为保持不变。
3. 修复 Linux 打包版启动及“学校原始页面”无法拉起浏览器的问题。程序会正确识别 Nuitka 编译态，并从 Linux 外部子进程环境中过滤 OpenCV 导入产生的空库路径和发布目录条目，避免捆绑 OpenSSL 遮蔽系统库。
4. Linux 浏览器入口使用无 shell 的 `xdg-open`，失败时回退 `gio open`；WebVPN 受控浏览器使用相同隔离环境，Windows 与 macOS 行为不变。
5. “学校原始页面”改为浏览器真实链接，即使系统 opener 不可用也能直接访问；后端程序化入口仍保留固定公开 URL。
6. Linux Release 构建新增真实产物冒烟测试，验证外部子进程环境不含空路径或发布目录，并确认 ddddocr、OpenCV 与 ONNX Runtime 仍能初始化。
7. 保留 v3.6.1 的可配置失败阈值：爆发和一般模式均可填写 1 至 1,000,000 次或设为“无限次”，网络异常和学校 5xx 不计入业务失败。
8. 单门课程连续未知响应的保护性暂停阈值由 200 次提高到 2000 次；中间收到一次可识别响应即清零，网络异常、阶段门控和会话恢复继续使用独立保护。
9. 保留任务暂停后增删、重试、开关与优先级调整、安全停止、课表、学分统计、多校区目录和账号隔离缓存。
10. OCR 自动重登录兼容 `ddddocr 1.6.1` 多种 API；CI 覆盖 Python 3.13/3.14，各平台构建前均真实初始化 OCR。
11. Release 运行数据继续位于系统用户目录，升级后沿用原有清单、Card Key 身份和安全课程缓存。
12. 学校密码只保存在当前进程内存中；WebVPN 只用于认证后的只读查询，选课提交固定使用学校主站，本版不提供自动退课。
13. 自动测试全部使用假数据，不访问学校，也不执行选课或退课操作。
14. Release 只提供各平台与源码 ZIP，不附带独立 `.sha256` 或 `SHA256SUMS.txt` 文件。

| 系统 | 下载文件 | 启动方式 |
| --- | --- | --- |
| Windows 10/11 64 位 | `SZU-Course-Help-v3.6.2-windows-x64.zip` | 双击 `启动抢课助手.bat` |
| Apple 芯片 Mac | `SZU-Course-Help-v3.6.2-macos-arm64.zip` | 双击 `启动抢课助手.command` |
| Intel 芯片 Mac | `SZU-Course-Help-v3.6.2-macos-x64.zip` | 双击 `启动抢课助手.command` |
| Linux 64 位 | `SZU-Course-Help-v3.6.2-linux-x64.zip` | 运行 `启动抢课助手.sh` |

每个发布包均含可执行程序、平台启动脚本、`使用手册.md`、`使用手册.pdf`、`更新记录.md`、项目说明和许可证。`SZU-Course-Help-v3.6.2-source.zip` 供开发者使用。

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
