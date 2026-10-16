# gauguin + KernelSU-Next (legacy) kernel build

云端编译 [Redmi Note 9 Pro 5G (gauguin / gauguinpro)](https://github.com/PixelOS-Devices/android_device_xiaomi_gauguin) 的 PixelOS 16.2 内核，
集成 [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next) `legacy` 分支（专为非 GKI / 老内核维护）。

## 精确版本锁定

| 组件 | 版本 |
|---|---|
| 内核源码 | `PixelOS-Devices/android_kernel_xiaomi_gauguin` @ `a0a88748828bdf4ad9a66c09fab9dd29e566e721` |
| 内核版本 | 4.19.325-cip133-st17（与设备 `uname -a` 中的 `ga0a88748828b` 一致） |
| 设备树 config | `vendor/lito-perf_defconfig` + `vendor/xiaomi/gauguin.config` |
| KernelSU-Next | `KernelSU-Next/KernelSU-Next` @ `legacy` 分支 |
| KSU hook 模式 | `CONFIG_KSU_SYSCALL_TABLE_HOOK`（不需要 KPROBES，要求内核 >= 4.17） |
| 管理器 APK | `KernelSU_Next_v3.4.2_33355-release.apk`（版本号用 `KSU_VERSION_OVERRIDE=33355` 对齐） |
| 工具链 | AOSP prebuilt `clang-r563880c`（与设备内核 `CONFIG_CC_VERSION_TEXT` 完全一致） |

## 为什么不用官方 KernelSU v3.3.1

官方自 v1.0 起放弃非 GKI 支持；其 `hook/arm64/patch_memory.c` 直接调用 `p4d_offset()`（Linux 4.20 才引入），
且全仓库没有任何 `< 5.0` 的兼容分支，4.19 无法编译。

KernelSU-Next 的 `legacy` 分支自带 `compat/` 兼容层，适配到 4.9/4.10/4.12/4.14/4.15/4.17，
并提供 `KSU_SYSCALL_TABLE_HOOK` 模式绕开 kprobes 依赖。

## 产出

`dist/Image` —— arm64 内核镜像，用于替换 ROM 包内 `boot.img` 的 kernel 区域。
