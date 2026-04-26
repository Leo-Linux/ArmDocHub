#!/usr/bin/env python3
"""
build-views.py
从 docs.tsv 生成 10 份虚拟化视图 markdown:
  - overview.md(系统虚拟化总览,八层结构)
  - application-vm-lifecycle.md(VM 生命周期,五阶段)
  - application-hypervisor-impl.md(Hypervisor 实现,八组件)
  - A-architecture-foundation.md ... G-confidential-computing.md(7 个方向视图)

用法:
  ./build-views.py [TSV 路径] [输出目录]
  默认:./docs.tsv -> ./arm-docs/views/
"""
from __future__ import annotations
import sys
import csv
import os
from pathlib import Path
from collections import defaultdict
from typing import Optional

# ---------- 配置 ----------

# 视图元数据
VIEW_META = {
    "A": {
        "title": "架构基础",
        "filename": "A-architecture-foundation.md",
        "intro": "任何虚拟化方向的起点。这一组文档定义了 ARM 架构的根:权威规范、异常模型、编程模型。\n\n所有其他视图都会引用其中至少一份。",
    },
    "B": {
        "title": "CPU 虚拟化",
        "filename": "B-cpu-virtualization.md",
        "intro": "EL2、HCR_EL2、VTCR_EL2、VHE、Nested 等 CPU 级虚拟化机制。\n\n核心问题:hypervisor 怎么虚拟化 CPU 状态、怎么陷入、怎么注入异常。",
    },
    "C": {
        "title": "内存虚拟化",
        "filename": "C-memory-virtualization.md",
        "intro": "Stage 2 地址翻译、VMID、TLB 维护、内存属性继承。\n\n核心问题:guest 物理地址 (IPA) 如何翻译到主机物理地址 (PA)。",
    },
    "D": {
        "title": "中断虚拟化",
        "filename": "D-interrupt-virtualization.md",
        "intro": "vGIC、GICH/GICV、vLPI/vSGI 直接注入、虚拟 timer。\n\n核心问题:hypervisor 怎么把物理中断或 software-generated 中断送给 guest vCPU。",
    },
    "E": {
        "title": "I/O 虚拟化",
        "filename": "E-io-virtualization.md",
        "intro": "SMMUv3、StreamID、PASID、DMA 隔离、设备直通(VFIO/IOMMUFD)。\n\n核心问题:让 guest 直接驱动物理设备而不破坏隔离。",
    },
    "F": {
        "title": "资源 QoS",
        "filename": "F-resource-qos.md",
        "intro": "MPAM 内存系统资源分区与监控:cache 容量、内存带宽 QoS。\n\n核心问题:多 VM 共享物理机时如何避免吵闹邻居 (noisy neighbor)。",
    },
    "G": {
        "title": "ARM 机密计算",
        "filename": "G-confidential-computing.md",
        "intro": "ARM CCA(Realm + RMM)+ TrustZone。\n\n核心问题:如何在不信任 hypervisor 的前提下保护 VM 内的敏感数据(机密计算)。",
    },
}

OVERVIEW_LAYERS = [
    {"num": 1, "title": "架构基础", "desc": "所有上层依赖的根。任何虚拟化方向都要先读这一层。"},
    {"num": 2, "title": "系统虚拟化总论", "desc": "虚拟化机制描述 + ABI 接口 + 系统级合规要求。"},
    {"num": 3, "title": "内存虚拟化(Stage 2)", "desc": "guest IPA → 主机 PA 的二级翻译。"},
    {"num": 4, "title": "中断虚拟化(vGIC)", "desc": "GIC 提供的虚拟中断注入和路由机制。"},
    {"num": 5, "title": "I/O 虚拟化(SMMU)", "desc": "DMA 设备的地址空间隔离。"},
    {"num": 6, "title": "资源 QoS(MPAM)", "desc": "多 VM 共享内存系统资源时的性能隔离。"},
    {"num": 7, "title": "ARM 机密计算", "desc": "Realm + RMM + TrustZone,机密虚拟化。"},
    {"num": 8, "title": "实现参考", "desc": "Neoverse CPU、CMN-700、GIC-700 等 IP TRM。"},
]

# 应用视图的阶段/组件结构(手工设计的章节)
VM_LIFECYCLE_STAGES = [
    {
        "title": "阶段 1:Hypervisor 启动 + 进入 EL2",
        "doc_ids": ["ddi0487-detail", "den0028-smccc", "102142-virt"],
        "note": "从 EL3 firmware 切换到 EL2,初始化虚拟化控制寄存器。",
    },
    {
        "title": "阶段 2:vCPU 创建",
        "doc_ids": ["102142-virt", "101811-mmu-detail", "102412-exception"],
        "note": "VMID 分配、Stage 2 页表初始化、异常向量表。",
    },
    {
        "title": "阶段 3:VM 启动(Reset → Guest OS)",
        "doc_ids": ["den0022-psci", "den0044-bbr", "den0029-sbsa", "den0094-bsa"],
        "note": "PSCI CPU_ON 启动 secondary CPU,VM 进入 firmware 然后到 OS。",
    },
    {
        "title": "阶段 4:VM 运行时事件",
        "doc_ids": ["198134-gicv3v4-virt", "102142-virt", "ihi0070-smmuv3"],
        "note": "中断注入、trap-and-emulate、DMA 处理。",
    },
    {
        "title": "阶段 5:VM 暂停 / 关机 / 销毁",
        "doc_ids": ["den0022-psci", "den0137-rmm"],
        "note": "PSCI CPU_OFF/SUSPEND/SYSTEM_OFF;Realm 场景额外走 RMI_REALM_DESTROY 清理内存。",
    },
]

HYPERVISOR_COMPONENTS = [
    {
        "title": "1. 陷入与异常处理",
        "doc_ids": ["ddi0487-detail", "102412-exception", "102142-virt"],
        "code": "arch/arm64/kvm/hyp/、arch/arm64/kvm/handle_exit.c",
    },
    {
        "title": "2. vCPU 状态切换(world switch)",
        "doc_ids": ["102142-virt", "ddi0487-detail"],
        "code": "arch/arm64/kvm/hyp/{vhe,nvhe}/",
    },
    {
        "title": "3. Stage 2 内存管理",
        "doc_ids": ["101811-mmu-detail", "102416-mmu-examples", "102142-virt"],
        "code": "arch/arm64/kvm/mmu.c",
    },
    {
        "title": "4. vGIC 实现",
        "doc_ids": ["ihi0069-gicv3v4", "198134-gicv3v4-virt", "102923-lpi", "dai0492-sw"],
        "code": "arch/arm64/kvm/vgic/",
    },
    {
        "title": "5. Timer 虚拟化",
        "doc_ids": ["102379-timer", "102142-virt"],
        "code": "arch/arm64/kvm/arch_timer.c",
    },
    {
        "title": "6. Hypercall 处理",
        "doc_ids": ["den0028-smccc", "den0022-psci"],
        "code": "arch/arm64/kvm/{psci,hypercalls}.c",
    },
    {
        "title": "7. 设备直通(SMMU + ITS)",
        "doc_ids": ["ihi0070-smmuv3", "109242-smmu-intro", "102923-lpi"],
        "code": "drivers/iommu/arm/arm-smmu-v3/",
    },
    {
        "title": "8. CCA / Realm 支持",
        "doc_ids": ["den0129-rme", "den0137-rmm", "102842-cca-sw"],
        "code": "arch/arm64/kvm/rme.c (2024 后逐步合入)",
    },
]


# ---------- 数据加载 ----------

def load_tsv(path: Path) -> list[dict]:
    """读取 TSV,返回 dict 列表。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 6:
                continue
            row = {
                "category": parts[0],
                "id": parts[1],
                "doc_id": parts[2],
                "title": parts[3],
                "url": parts[4],
                "type": parts[5],
                "views": parts[6] if len(parts) > 6 else "",
                "role": parts[7] if len(parts) > 7 else "",
                "note": parts[8] if len(parts) > 8 else "",
            }
            rows.append(row)
    return rows


def category_label(cat: str) -> str:
    """01-arm-architecture/1.1-arm-arm -> [一/1.1]"""
    main, sub = cat.split("/", 1)
    main_num = main.split("-", 1)[0]
    sub_num = sub.split("-", 1)[0]
    cn_nums = {"01": "一", "02": "二", "03": "三", "04": "四", "05": "五", "06": "六"}
    return f"[{cn_nums.get(main_num, main_num)}/{sub_num}]"


def doc_in_view(row: dict, view_tag: str) -> bool:
    """判断 row 是否属于 view_tag(逗号分隔的 views 字段)。"""
    views = [v.strip() for v in row["views"].split(",") if v.strip()]
    return view_tag in views


def find_doc(rows: list[dict], doc_id: str) -> Optional[dict]:
    """按 id 查找一份文档。"""
    for r in rows:
        if r["id"] == doc_id:
            return r
    return None


def fmt_doc_line(row: dict, with_role: bool = True) -> str:
    """格式化一行文档引用。"""
    label = category_label(row["category"])
    line = f"- `{label}` **{row['doc_id']}** — {row['title']}"
    if with_role and row.get("role"):
        line += f" *[{row['role']}]*"
    if row.get("note"):
        line += f"  \n  {row['note']}"
    return line


# ---------- 视图生成 ----------

def build_direction_view(view_tag: str, rows: list[dict], outdir: Path) -> None:
    """生成方向视图 A–G。"""
    meta = VIEW_META[view_tag]
    matching = [r for r in rows if doc_in_view(r, view_tag)]

    # 按 role 分组
    by_role = defaultdict(list)
    for r in matching:
        role = r["role"] or "其他"
        by_role[role].append(r)

    role_order = ["核心", "相关", "背景", "备查", "其他"]

    lines = [
        f"# 视图 {view_tag}:{meta['title']}",
        "",
        meta["intro"],
        "",
        "---",
        "",
    ]

    for role in role_order:
        if role not in by_role:
            continue
        lines.append(f"## {role}")
        lines.append("")
        for r in by_role[role]:
            lines.append(fmt_doc_line(r, with_role=False))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*共 {len(matching)} 份文档。*")

    (outdir / meta["filename"]).write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ {meta['filename']}({len(matching)} 份)")


def build_overview(rows: list[dict], outdir: Path) -> None:
    """生成总览 overview.md(按八层组织)。"""
    in_overview = [r for r in rows if doc_in_view(r, "overview")]

    # 按物理子类把文档分组到层
    layer_docs = defaultdict(list)

    def assign_layer(r: dict) -> int:
        cat = r["category"]
        # 第 1 层:架构基础(1.1 ARM ARM、1.2 Exception Model 中和系统虚拟化基础相关的)
        # 第 2 层:系统虚拟化总论(102142 + 1.4 接口 + 1.3 系统级)
        # 第 3 层:内存虚拟化(2.1 + 2.2)
        # 第 4 层:中断虚拟化(3.1 + 3.2 + 3.3)
        # 第 5 层:I/O 虚拟化(2.3 SMMU)
        # 第 6 层:资源 QoS(2.4 MPAM)
        # 第 7 层:ARM 机密计算(4.1 + 4.2)
        # 第 8 层:实现参考(5.x + 3.4)

        if cat == "06-virtualization/6.1-system-virtualization":
            return 2
        if cat.startswith("01-arm-architecture/1.4") or cat.startswith("01-arm-architecture/1.3"):
            return 2
        if cat.startswith("01-arm-architecture/"):
            return 1
        if cat.startswith("02-memory/2.1") or cat.startswith("02-memory/2.2"):
            return 3
        if cat.startswith("02-memory/2.3"):
            return 5
        if cat.startswith("02-memory/2.4"):
            return 6
        if cat.startswith("03-interrupt/3.1") or cat.startswith("03-interrupt/3.2") or cat.startswith("03-interrupt/3.3"):
            return 4
        if cat.startswith("03-interrupt/3.4"):
            return 8
        if cat.startswith("04-security/"):
            return 7
        if cat.startswith("05-server/"):
            return 8
        return 0

    for r in in_overview:
        layer = assign_layer(r)
        if layer:
            layer_docs[layer].append(r)

    lines = [
        "# 系统虚拟化总览",
        "",
        "本文档是 ARM 官方文档归档库的**入口和地图**。按系统虚拟化栈的八层组织,",
        "回答「整本书需要的全部 ARM 官方资料是哪些」。",
        "",
        "每份文档后的 `[类/子类]` 标签指向物理归档位置。",
        "",
        "---",
        "",
    ]

    for layer in OVERVIEW_LAYERS:
        num = layer["num"]
        docs = layer_docs.get(num, [])
        lines.append(f"## 第 {num} 层:{layer['title']}")
        lines.append("")
        lines.append(layer["desc"])
        lines.append("")
        if not docs:
            lines.append("*(本层暂无文档)*")
        else:
            for r in docs:
                lines.append(fmt_doc_line(r, with_role=False))
        lines.append("")

    total = sum(len(v) for v in layer_docs.values())
    lines.extend([
        "---",
        "",
        f"## 统计",
        "",
        f"总览主链路共 **{total}** 份文档。",
        "",
        "## 配套视图",
        "",
        "- **方向视图**(按机制方向切片)",
        "  - [A. 架构基础](A-architecture-foundation.md)",
        "  - [B. CPU 虚拟化](B-cpu-virtualization.md)",
        "  - [C. 内存虚拟化](C-memory-virtualization.md)",
        "  - [D. 中断虚拟化](D-interrupt-virtualization.md)",
        "  - [E. I/O 虚拟化](E-io-virtualization.md)",
        "  - [F. 资源 QoS](F-resource-qos.md)",
        "  - [G. ARM 机密计算](G-confidential-computing.md)",
        "- **应用视图**(按使用场景切片)",
        "  - [VM 生命周期](application-vm-lifecycle.md)",
        "  - [Hypervisor 实现](application-hypervisor-impl.md)",
    ])

    (outdir / "overview.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ overview.md({total} 份覆盖)")


def build_vm_lifecycle(rows: list[dict], outdir: Path) -> None:
    """生成 VM 生命周期视图。"""
    lines = [
        "# 应用视图:VM 生命周期",
        "",
        "按 VM 从创建到销毁的时间序组织文档。**横切多个机制**——同一份文档",
        "(如 PSCI)在多个阶段被引用,因为 VM 启动和关机都用它。",
        "",
        "**适用场景**:写 Chapter 17 「VM 创建全路径」、KVM/QEMU 启动流程分析。",
        "",
        "---",
        "",
    ]

    for stage in VM_LIFECYCLE_STAGES:
        lines.append(f"## {stage['title']}")
        lines.append("")
        lines.append(stage["note"])
        lines.append("")
        for did in stage["doc_ids"]:
            r = find_doc(rows, did)
            if r:
                lines.append(fmt_doc_line(r, with_role=False))
            else:
                lines.append(f"- *(未找到 doc_id={did})*")
        lines.append("")

    (outdir / "application-vm-lifecycle.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ application-vm-lifecycle.md")


def build_hypervisor_impl(rows: list[dict], outdir: Path) -> None:
    """生成 Hypervisor 实现视图。"""
    lines = [
        "# 应用视图:Hypervisor 实现",
        "",
        "从 KVM/Xen/pKVM 实现者的视角组织文档。每个 hypervisor 内部组件",
        "对应:**ARM 规范文档** + **Linux 内核源码路径**。",
        "",
        "**适用场景**:写 KVM 内核子系统分析、pKVM 设计章节、hypervisor 选型对比。",
        "",
        "---",
        "",
    ]

    for comp in HYPERVISOR_COMPONENTS:
        lines.append(f"## {comp['title']}")
        lines.append("")
        for did in comp["doc_ids"]:
            r = find_doc(rows, did)
            if r:
                lines.append(fmt_doc_line(r, with_role=False))
            else:
                lines.append(f"- *(未找到 doc_id={did})*")
        lines.append("")
        lines.append(f"**KVM 代码**:`{comp['code']}`")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Hypervisor 实现对比简表",
        "",
        "| 组件 | KVM(VHE) | KVM(non-VHE) | pKVM | Xen on ARM |",
        "|------|----------|--------------|------|-----------|",
        "| 陷入处理 | √ | √ | √ | √ |",
        "| Stage 2 | √ | √ | √(独立 hyp) | √ |",
        "| vGIC | √(software) | √(software) | √(software) | √ |",
        "| 直接注入 vIRQ | GICv4.1 可选 | GICv4.1 可选 | GICv4.1 可选 | √ |",
        "| RMM 集成 | 进行中 | 不支持 | 不支持 | 不支持 |",
        "",
    ])

    (outdir / "application-hypervisor-impl.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ application-hypervisor-impl.md")


# ---------- 主程序 ----------

def main():
    tsv_path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs.tsv")
    outdir = Path(sys.argv[2] if len(sys.argv) > 2 else "arm-docs/views")

    if not tsv_path.exists():
        print(f"ERROR: TSV not found at {tsv_path}", file=sys.stderr)
        sys.exit(1)

    outdir.mkdir(parents=True, exist_ok=True)

    print(f"读取 TSV: {tsv_path}")
    rows = load_tsv(tsv_path)
    print(f"  载入 {len(rows)} 条记录")

    print(f"\n生成视图到: {outdir}")
    build_overview(rows, outdir)
    build_vm_lifecycle(rows, outdir)
    build_hypervisor_impl(rows, outdir)
    for tag in ["A", "B", "C", "D", "E", "F", "G"]:
        build_direction_view(tag, rows, outdir)

    print(f"\n完成。共生成 10 份视图文档。")


if __name__ == "__main__":
    main()
