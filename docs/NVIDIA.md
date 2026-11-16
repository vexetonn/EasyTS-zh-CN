# NVIDIA 自定义分辨率

VEX 使用 NVIDIA 驱动提供的公开 NVAPI，自动创建主显示器缺少的分辨率。接口与结构体参考 NVIDIA/nvapi 提交 `51e5aae4bc40c3ccd3fb7d4dfd94256e7bfc496e` 的 `nvapi.h`、`nvapi_interface.h` 及官方 `Sample_Code/CustomTiming/CustomTiming.cpp`。

1. 从 Windows 的主显示器名称定位 NVIDIA display ID，不会任选另一块显卡或显示器。
2. 检查 Windows 是否已经提供目标宽、高和当前刷新率。已经存在时直接使用。
3. 缺少时读取当前精确刷新率，按官方示例用 CVT Reduced Blanking 计算时序。
4. 调用 `NvAPI_DISP_TryCustomDisplay` 测试，成功后 `NvAPI_DISP_SaveCustomDisplay` 保存，并始终调用 `NvAPI_DISP_RevertCustomDisplayTrial` 退出临时测试。
5. 再次检查 Windows 是否实际报告目标模式，随后才禁用监视器并切换。仅在驱动返回权限不足时，通过程序自身的受限辅助入口请求管理员权限；辅助入口只接受宽、高数字，不执行任意脚本或写入任意文件。
6. 首次创建的模式应用后，需要在 20 秒内确认画面正常。未确认时先恢复原分辨率，再处理需要管理员权限的监视器恢复。已创建的自定义模式保留在 NVIDIA 驱动中，恢复桌面不会删除它。

自动创建仅适用于主显示器由 NVIDIA 驱动直接控制、且驱动接受的配置。部分混合显卡笔记本、远程或虚拟显示连接以及其他显卡无法自动创建，程序会停止并显示原因。已有显示模式仍可正常切换。全屏缩放和游戏内显示选项仍由用户设置。

软件只加载系统 `System32\nvapi64.dll`，不会附带 NVIDIA 驱动或下载驱动程序。相关接口定义许可见 [NVIDIA-NVAPI.txt](../THIRD_PARTY_LICENSES/NVIDIA-NVAPI.txt)。

验证包括结构体大小与偏移、真实驱动只读初始化、主显示器识别、当前时序查询与目标时序计算，以及模拟的测试/保存/恢复、失败、权限和超时流程。没有在开发检查中实际创建显示模式、禁用监视器或修改当前分辨率。

参考：[NVIDIA 官方接口说明](https://docs.nvidia.com/nvapi/group__dispcontrol.html)、[官方 SDK 与示例](https://github.com/NVIDIA/nvapi/tree/51e5aae4bc40c3ccd3fb7d4dfd94256e7bfc496e)。
