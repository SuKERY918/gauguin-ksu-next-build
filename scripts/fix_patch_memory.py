#!/usr/bin/env python3
"""移除 KernelSU-Next legacy 分支 patch_memory.c 中不必要且有有害副作用的兼容宏。

问题
----
patch_memory.c 在 `#include "linux/uaccess.h"` **之前**定义了函数式宏：

    // copy_to_kernel_nofault() was introduced in 5.8; before that it was
    // named probe_kernel_write()
    #if LINUX_VERSION_CODE < KERNEL_VERSION(5, 8, 0)
    #define copy_to_kernel_nofault(dst, src, size) \
        probe_kernel_write((dst), (src), (size))
    #endif

注释假设「5.8 以下内核没有 copy_to_kernel_nofault」，但本设备内核
（PixelOS gauguin 4.19.325，mm/maccess.c:50）**已经 backport 并实现了**
copy_to_kernel_nofault，uaccess.h:306 也声明了它。于是在 4.19 上该宏
反而把这一行声明：

    long notrace copy_to_kernel_nofault(void *dst, const void *src, size_t size);

展开成

    long notrace probe_kernel_write((void *dst), (const void *src), (size_t size));

clang 随即在三个参数类型处报
    error: type specifier missing, defaults to 'int' [-Werror,-Wimplicit-int]
又因为内核配置 CONFIG_CC_WERROR=y，编译直接失败。

修法
----
删除该宏，让代码直接调用内核提供的真函数（内置 CONFIG_KSU=y，无需导出符号）。
脚本幂等：若已无该宏则直接跳过。
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else \
    "kernel/drivers/kernelsu/hook/patch_memory.c"

with open(path, encoding="utf-8") as fh:
    src = fh.read()

if "#define copy_to_kernel_nofault" not in src:
    print("[skip] patch_memory.c 中已无 copy_to_kernel_nofault 宏")
    sys.exit(0)

macro_re = re.compile(
    r"[ \t]*// copy_to_kernel_nofault\(\) was introduced in 5\.8; before that it was\n"
    r"[ \t]*// named probe_kernel_write\(\)\n"
    r"[ \t]*#if LINUX_VERSION_CODE < KERNEL_VERSION\(5, 8, 0\)\n"
    r"[ \t]*#define copy_to_kernel_nofault\(dst, src, size\)[^\n]*\n"
    r"[^\n]*probe_kernel_write\(\(dst\), \(src\), \(size\)\)[^\n]*\n"
    r"[ \t]*#endif\n"
)

m = macro_re.search(src)
if m is None:
    print("[error] 未找到预期的宏定义块，格式可能已变化", file=sys.stderr)
    sys.exit(1)

src = src[:m.start()] + src[m.end():]

with open(path, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(src)

print("[ok] 已移除 patch_memory.c 中的 copy_to_kernel_nofault 兼容宏")
print("     （内核 mm/maccess.c 已提供该函数，KSU 将直接调用它）")
