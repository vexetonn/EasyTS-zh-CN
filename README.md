# EasyTS 中文一键版

**原作者：[ahhmilo](https://github.com/ahhmilo) · 原项目：[ahhmilo/EasyTS](https://github.com/ahhmilo/EasyTS)**

基于 EasyTS v4.2.0 的中文界面与一键操作修改版，由 [vexetonn](https://github.com/vexetonn) 发布。完整版权及修改说明见 [ATTRIBUTION.md](ATTRIBUTION.md)，原始 [LICENSE](LICENSE) 保持不变。

## 下载即用

**[下载单文件 EXE](https://github.com/vexetonn/EasyTS-zh-CN/releases/download/v4.2.0-zh-CN.2/EasyTS-zh-CN-v4.2.0.2.exe)** · **[下载便携压缩包](https://github.com/vexetonn/EasyTS-zh-CN/releases/download/v4.2.0-zh-CN.2/EasyTS-zh-CN-v4.2.0.2-portable.zip)** · [全部发布版本](https://github.com/vexetonn/EasyTS-zh-CN/releases)

Windows 10/11 x64。双击即可运行，无需安装 Python。若缺少 Microsoft WebView2，程序会提供安装引导。

![中文一键版主界面](assets/main_page.png)

## 使用方法

1. 首次在显卡控制面板准备目标自定义分辨率，并设置全屏缩放。
2. 退出其他版本 EasyTS，在启动游戏前输入目标分辨率，点击 **一键开启拉伸**，允许 Windows 管理员操作。
3. 程序会先禁用当前已启用的监视器，再切换分辨率。完成后启动《无畏契约》，游戏内选择窗口化全屏和填充。
4. 用完点击 **一键恢复桌面**，恢复最初保存的分辨率并启用本次禁用的监视器。

默认开启退出游戏后自动恢复，需保持 EasyTS 运行，并允许恢复时的管理员操作。开启前已经禁用的设备会保持原状。默认 `Ctrl + Alt + S` 只切换分辨率，便于菜单和对局之间切换。

常用分辨率和预设用于填入输入框；“仅切分辨率”保留单独切换功能。恢复未完成时记录会保留，可重试；意外关闭后重新打开也可继续恢复。

本版会处理全部当前连接且已启用的监视器。部分笔记本禁用期间无法调节亮度。实际拉伸效果取决于显卡和游戏设置。

## 说明与构建

- [详细中文说明与构建步骤](README.zh-CN.md)
- [修改记录](CHANGELOG.zh-CN.md)
- [原作者英文说明](README.upstream.md)
- [验证记录](验证记录.json)：48 项模拟和脚本检查、20 类界面验证及 Windows 独立启动验证通过。没有进行真实设备禁用或游戏内效果实测。

个人配置保存在 `%LOCALAPPDATA%\EasyTS`；本仓库和发布包不包含个人配置。

## 许可与致谢

感谢 **ahhmilo** 创作 EasyTS。本项目保留原作者历史、原始版权和专有软件许可证。使用、修改和再分发应遵守 [LICENSE](LICENSE) 与作者的具体授权范围。第三方依赖许可见 [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES)。
