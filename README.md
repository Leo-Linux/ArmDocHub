# ARM 官方文档归档系统

用双层架构管理 ARM 官方文档。

## 设计原则

**两层结构**:
- **物理路径**(归档位置):每份文档只放一处。六大类、17 子类、61 份文档。
- **虚拟化视图**(逻辑引用):跨类组合的引用清单,每份文档可被多个视图引用。

物理树 + 视图图,各司其职。

## 文件组成

```
.
├── README.md              ← 本文件
├── docs.tsv               ← 数据源:47 份文档的元数据(TAB 分隔)
├── fetch-arm-docs.sh      ← 下载脚本:按物理路径归档文件
└── build-views.py         ← 视图生成器:从 TSV 生成 10 份视图 markdown
```

## 用法

### 第一次运行

```bash
# 1. 下载所有文档(直链 PDF + HTML 详情页)
chmod +x fetch-arm-docs.sh
./fetch-arm-docs.sh

# 2. 生成虚拟化视图
python3 build-views.py docs.tsv arm-docs/views

# 3. 查看入口
open arm-docs/views/overview.md
```

### 输出目录结构

```
arm-docs/
├── 01-arm-architecture/        # 一、ARM 架构(14 份)
│   ├── 1.1-arm-arm/
│   ├── 1.2-exception-model/
│   ├── 1.3-system-architecture/
│   └── 1.4-firmware-interfaces/
├── 02-memory/                  # 二、内存(16 份)
│   ├── 2.1-memory-model/
│   ├── 2.2-mmu/
│   ├── 2.3-smmu/
│   └── 2.4-mpam/
├── 03-interrupt/               # 三、中断(10 份)
│   ├── 3.1-gic-architecture/
│   ├── 3.2-gic-guides/
│   ├── 3.3-generic-timer/
│   └── 3.4-gic-ip-trm/
├── 04-security/                # 四、安全(9 份)
│   ├── 4.1-cca-realm/
│   └── 4.2-trustzone/
├── 05-server/                  # 五、服务器(11 份)
│   ├── 5.1-neoverse-trm/
│   └── 5.2-interconnect-trm/
├── 06-virtualization/          # 六、虚拟化(1 份)
│   └── 6.1-system-virtualization/
├── views/                      # 虚拟化视图(10 份)
│   ├── overview.md             ← 入口:系统虚拟化总览(8 层)
│   ├── application-vm-lifecycle.md
│   ├── application-hypervisor-impl.md
│   ├── A-architecture-foundation.md
│   ├── B-cpu-virtualization.md
│   ├── C-memory-virtualization.md
│   ├── D-interrupt-virtualization.md
│   ├── E-io-virtualization.md
│   ├── F-resource-qos.md
│   └── G-confidential-computing.md
├── manifest.csv                ← 全量记录(下载状态、SHA256)
├── MISSING.md                  ← 需手动下载的清单
└── download.log                ← 下载日志
```

## 视图结构

```
■ 总览(顶层入口,1 份)
    overview.md  按系统虚拟化栈八层组织

■ 应用视图(按使用场景,2 份)
    application-vm-lifecycle.md     按 VM 时间序(5 阶段)
    application-hypervisor-impl.md  按 hypervisor 组件(8 组件 + 代码路径)

■ 方向视图(按机制方向,7 份:A–G)
    A. 架构基础       任何方向的起点
    B. CPU 虚拟化     EL2 / HCR_EL2 / VHE / Nested
    C. 内存虚拟化     Stage 2 / VMID / TLB
    D. 中断虚拟化     vGIC / vLPI / vSGI
    E. I/O 虚拟化     SMMU / StreamID / 设备直通
    F. 资源 QoS       MPAM 分区与监控
    G. ARM 机密计算   CCA + Realm + RMM + TrustZone
```

## 文档收录边界


不收录:
- 单机软件防护(MTE / PAC / BTI 综合指南)— 与虚拟化主题无关
- 过时的 GIC 实现 IP TRM(GIC-400/500/600)— Neoverse 已用 GIC-700
- 已被替代的架构规范(GICv2 IHI 0048)

边界保留:
- DDI 0587 RAS — 标记 `[备查]`,物理保留但不入主链路
- IHI 0062 SMMUv2 — 仅供与 SMMUv3 对比
- 101206 GIC-600AE — 功能安全版本,涉车场景使用

## 维护

### 新增文档

在 `docs.tsv` 增加一行,九个 TAB 分隔字段:
```
category    id    doc_id    title    url    type    views    role    note
```

`views` 列填该文档要进入的视图标签(逗号分隔):
- `overview` — 系统虚拟化总览
- `A` 到 `G` — 七个方向视图
- `app-lifecycle` / `app-hyp-impl` — 仅供阅读,不参与脚本生成
- `(无)` — 显式标注:文档纯存档,与虚拟化无关,不进任何视图

> 注:应用视图(`application-vm-lifecycle.md` / `application-hypervisor-impl.md`)
> 由 `build-views.py` 内部 curated 列表生成,需要"阶段顺序"和"组件分组"
> 这两类语义,纯 tag 表达不出来。`app-lifecycle` / `app-hyp-impl` 这两个
> tag 留在 TSV 中只是给人读时的索引提示,改它们不会影响视图输出 ——
> 要调整应用视图,直接改 `build-views.py` 里的 `VM_LIFECYCLE_STAGES` /
> `HYPERVISOR_COMPONENTS`。

然后重跑 `fetch-arm-docs.sh` 和 `build-views.py`。

### 移除文档

删除 `docs.tsv` 对应行,重跑两个脚本。已下载的文件不会被自动删除——手动清理即可。

### Arm 文档版本更新

ARM 官方 URL 通常带 `/latest/`,会自动跳到最新。如需固定版本,改 URL 中的版本号(如 `/Ja/`)。`documentation-service.arm.com/static/<hash>` 的 hash 会随版本变化,失效时回详情页重新拿。
