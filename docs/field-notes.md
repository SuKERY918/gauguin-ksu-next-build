# 实机诊断记录：KernelSU-Next legacy 在 gauguin (4.19.325) 上的 hook 模式选择

本文记录本次 root 过程中在真机上得到的结论，供后续复现参考。

## 环境

| 项 | 值 |
|---|---|
| 设备 | Redmi Note 9 Pro 5G（gauguinpro / M2007J17C），A-only，bootloader 已解锁 |
| ROM | PixelOS 16.2 (Android 16 / SDK 36)，`PixelOS_gauguin-16.2-20260613-1146` |
| 内核 | `4.19.325-cip133-st17-perf`，源码 commit `a0a88748828bdf4ad9a66c09fab9dd29e566e721` |
| 关键配置 | `PGTABLE_LEVELS=3`、`ARM64_VA_BITS=39`、`STRICT_KERNEL_RWX=y`、`CC_WERROR=y`、`FRAME_WARN=2048`、`LTO_CLANG=y`、`CFI_CLANG=y`、`SHADOW_CALL_STACK=y`、`KPROBES` 未开 |
| KSU | KernelSU-Next `legacy` 分支（d51ca52）+ 管理器 v3.4.2 (33355) |

## 结论一：`CONFIG_KSU_SYSCALL_TABLE_HOOK` 在本内核上不可用（已实机验证）

首次刷入使用 syscall table hook 模式，内核日志（`adb logcat -b kernel`，内核配置未开
`CONFIG_SECURITY_DMESG_RESTRICT` 故可读）：

```
KernelSU: welcome to KernelSU version 33355
KernelSU: LSM hooks initialized.
KernelSU: hook_manager: initializing..
KernelSU: sth: sys_call_table=0xffffff92238009c8
KernelSU: sth: patch syscall 221: 0xffffff92222e1cd8 -> 0xffffff9222fd9a6c
KernelSU: failed to find phy addr for patch dst addr 0xffffff92238010b0
KernelSU: sth: patch syscall 221 failed
KernelSU: sth: patch syscall 281: ... failed
KernelSU: sth: patch syscall 48:  ... failed
KernelSU: sth: patch syscall 79:  ... failed
KernelSU: sth: 0/4 syscalls hooked
```

- 符号解析成功（`sys_call_table` 找到了，表项地址计算正确：`base + 221*8 = 0xffffff92238010b0`）；
- 失败点是 `phys_from_virt()` 无法由虚拟地址推出物理地址，因此 `ksu_patch_text()` 无法写入；
- 本内核 `PGTABLE_LEVELS=3` → `arch/arm64/include/asm/pgtable-types.h` 定义
  `__ARCH_USE_5LEVEL_HACK` 并包含 `pgtable-nopud.h` → 转而包含 `pgtable-nop4d-hack.h`
  → `p4d` 与 `pud` **同时折叠进 `pgd`**，`phys_from_virt()` 的 pgd→p4d→pud→pmd→pte 遍历在此结构下取不到 pte。

**后果**：该模式下 `execve/faccessat/newfstatat/reboot` 全部 hook 失败。
其中 **reboot syscall hook 是管理器安装 supercall fd 的唯一入口**，
因此管理器界面显示：

```
不支持 | 未集成
不支持非 GKI 内核。请将 KernelSU-Next 传统驱动程序集成到您的内核中！
```

**注意**：此模式下 **LSM hook 仍然正常**，日志里 `handle_setresuid` 会持续刷屏，
容易被误判为“KSU 正常工作”。判断依据应以 `sth: N/4 syscalls hooked` 为准。

## 结论二：改用 kprobes hook 模式

```
CONFIG_KPROBES=y
CONFIG_KRETPROBES=y
CONFIG_KPROBE_EVENTS=y
CONFIG_KSU=y
CONFIG_KSU_KPROBES_HOOK=y
# CONFIG_KSU_SYSCALL_TABLE_HOOK is not set
```

kprobes 模式走内核原生 `register_kprobe`，完全不触碰页表与 patch 内存，
绕开了 `phys_from_virt()`；同机型同内核版本已有成功案例。

## 结论三：关闭 LTO 带来的连锁配置变化（预期内）

为缩短构建时间关闭 `CONFIG_LTO_CLANG` 后，因 Kconfig 依赖链自动关闭：

| 项 | 原因 |
|---|---|
| `CONFIG_CFI_CLANG` / `CFI_CLANG_SHADOW` | `depends on LTO_CLANG` |
| `CONFIG_SHADOW_CALL_STACK` | 随 LTO/CFI 一起关闭 |
| `CONFIG_THINLTO` | `depends on LTO_CLANG` |

因此还需放宽编译容错（原厂 LTO 构建不会触发）：

```
# CONFIG_CC_WERROR is not set
CONFIG_FRAME_WARN=4096
```

否则会撞上：

```
drivers/power/supply/maxim/sha384_software.c:62:5: error:
  stack frame size (2912) exceeds limit (2048) in 'sha3_256_hmac'
  [-Werror,-Wframe-larger-than]
```

## 结论四：两个集成期的坑

1. **`kernel/include/uapi` 是符号链接**（指向仓库根的 `../../uapi`）。
   用 `cp -r` 集成时符号链接会被原样复制，在目标位置变成**断链**，
   导致 `uapi/feature.h`、`uapi/app_profile.h` 找不到。必须用 `cp -rL` 解引用，
   或显式把 `uapi/*.h` 铺到 `drivers/kernelsu/include/uapi/`。
2. **`patch_memory.c` 的宏污染**（仅 syscall table 模式相关）：
   它在 `#include <linux/uaccess.h>` **之前** `#define copy_to_kernel_nofault(dst,src,size) ...`，
   而本内核 `uaccess.h:306` 恰好声明了同名函数，声明被宏展开成
   `probe_kernel_write((void *dst), ...)`，clang 报
   `type specifier missing, defaults to 'int'`。本内核 `mm/maccess.c:50` 已实现该函数，
   直接删掉这个兼容宏即可。

## 结论五：boot.img 重打包

- 本机 boot.img 为 **Android boot header v2**（非 GKI），布局：
  `header(4096) | kernel(未压缩 ARM64 Image) | ramdisk(LZ4-legacy) | dtb |
  填充至分区大小 128MB`；
- 只需替换 **kernel 区域**，ramdisk 与 dtb 原样保留（差异审计：header 仅 kernel_size 与 id 变化）；
- `id` 字段是固定 32 字节：SHA1 占 20 字节 + 12 字节补零。
  用 Python 切片直接赋 20 字节会**缩短 header**、导致其后字段整体前移（dtb_size 读成 0）。
- ROM 内 `vbmeta.img` 的 flags = 3（`HASHTREE_DISABLED | VERIFICATION_DISABLED`），
  且不含 boot 分区 hash 描述符，因此替换 boot 不会触发 AVB 校验失败。
