# mh2max

把 MetaHuman（或已标准化的自定义角色）从 **Maya 一键导出到 3ds Max**：导入角色 → 烘焙面部 Morph → 导出 FBX → 在 Max 里自动装 Morpher 并接线。

**当前版本：1.3.31**  
目标环境：Maya 2022+ / 3ds Max 2022+（开发测试为 Maya 2026 + Max 2026）

---

## 能做什么

- **导入 MH**：从 UE 5.6+ DCC Export（ZIP 或已解压文件夹）导入，并用 MetaHuman for Maya 自动装配。
- **检测 / 标准化**：检查当前场景是否为可用角色；非标准角色可做标准化（不改原控制器/骨骼名）。
- **导出至 3ds Max**：烘焙单轴 Morph + 二维角落残差、导出 FBX、启动 Max 自动装配。
- **轴向对齐**：Maya 为 Y 向上，Max 为 Z 向上。导入时由 FBX 对整棵层级做轴转换（网格、骨骼、控制器、IK、蒙皮一起转），角色在 Max 里直立。
- **显示/隐藏控制器**、**检查更新**、可选的 **UE5 控制器同步**。

详细版本记录见仓库内 [`更新日志.txt`](更新日志.txt)。

---

## 需要事先安装的软件

本仓库 **不包含** 下列软件，需自行安装：

| 软件 | 用途 | 何时需要 |
|------|------|----------|
| Autodesk Maya 2022 或更高 | 导入、烘焙 Morph、导出 FBX | 始终 |
| Autodesk 3ds Max 2022 或更高 | 导入 FBX、装配 Morpher | 导出到 Max 时 |
| [MetaHuman for Maya](https://www.fab.com/listings/9e3bf55e-d4c3-44fc-a3d4-ec4cb772ec29)（Epic / Fab） | Character Assembler、RigLogic | 使用「导入 MH」时 |
| MetaHuman 角色包 | DCC Export 的 ZIP / 文件夹，或已装配的 Maya 场景 | 你的角色数据 |

仓库 Git 内 **不含** 约 1.5GB 的 MetaHuman for Maya 压缩包。请到 [Releases](https://github.com/Elijah-Neverdie/mh2max/releases) 下载 `MetaHumanForMaya-1.3.1-win64.zip`，放到本仓库的 `vendor/` 目录。参考文件见 `vendor/MetaHumanForMaya.mod`。

Maya 侧无需 pip 依赖。Max 侧使用内置 Morpher、FBX、OBJ。

---

## 一键安装（推荐）

1. 克隆或解压本仓库到任意路径（支持中文路径），例如 `C:\Users\A\Tools\mh2max`。
2. 从 [Releases](https://github.com/Elijah-Neverdie/mh2max/releases) 下载 `MetaHumanForMaya-1.3.1-win64.zip`，放入 `vendor/`。
3. 双击 **`install.bat`**。
   - 会扫描本机 Maya / Max 版本，默认全部安装。
   - 扫不到时，可粘贴 `.lnk` 快捷方式（支持多层嵌套）或 `3dsmax.exe` 路径。
   - 若安装了多个 Max 版本，可选择默认导出版本。
   - 配置写入 `%LOCALAPPDATA%\mh2max\config.json`。
4. **重启 Maya**。顶栏应出现 **MH2Max** 菜单（若已装 Epic 插件，也可能出现在 **MetaHuman** 菜单内）。

可选环境变量：

- `MH2MAX_EXE`：指定 `3dsmax.exe` 的完整路径。
- `MH2MAX_DHI_ROOT` 或 `DHI_ROOT`：旧版 DHI 根目录（仅 legacy，一般不需要）。

---

## 手动安装

1. 克隆本仓库，例如 `C:\Users\A\Tools\mh2max`。
2. 复制模块描述文件：

   ```text
   把 mh2max.mod.example 复制为
   %USERPROFILE%\Documents\maya\modules\mh2max.mod
   ```

   打开该文件，把第二行路径改成 **本机仓库的绝对路径**。

3. （推荐）把 `userSetup.example.py` 里的代码追加到 `Documents\maya\scripts\userSetup.py`，这样 Maya 主窗口起来后会自动装菜单，而不会卡住启动屏。
4. 按 Epic 文档安装 **MetaHuman for Maya** 到 `Documents\maya\modules\MetaHumanForMaya`。
5. 重启 Maya。

---

## 菜单更新了但 Maya 已经开着：如何重载

不必关 Maya。打开 **窗口 → 常规编辑器 → 脚本编辑器**，切到 **Python**，执行下面任一方式。

**方式 A：直接运行脚本**

```python
exec(open(r"C:\Users\A\Tools\mh2max\reload_menu.py", encoding="utf-8").read())
```

把路径改成你本机的仓库路径。

**方式 B：把文件拖进脚本编辑器**

把 `reload_menu.py` 拖进 Python 页签，再点执行。

成功时脚本编辑器会打印类似：

```text
[mh2max] File menu restored; use top menu MH2Max ...
```

顶栏菜单应显示 **mh2max v1.3.31**。

若「文件」菜单被旧版插件弄乱、只剩 MetaHuman 相关项：同样运行 `reload_menu.py`，它会恢复 Maya 自带的「文件」菜单。

---

## 日常用法

菜单顺序建议：**导入 MH**（或打开已有场景）→ **检测当前角色** → **导出至 3ds Max**。

未检测成功、也未导入成功时，「导出至 3ds Max」会保持禁用。

### 1. 导入 MH（UE 5.6+ DCC Export）

1. 先装好 Epic「MetaHuman for Maya」。
2. 菜单 **MH2Max → 导入 MH**，选 ZIP 或已解压文件夹。
3. 文件夹可以是导出根目录，也可以是它的父目录（会自动搜索 `ExportManifest.json` 或 `head.dna` + `body.dna`）。
4. 过程目录默认在源旁边：`MHI_<名称>\`。已存在时会询问是否覆盖，或自动用 `_2` 等后缀。
5. 装配依赖 Character Assembler；装好后可自动 Assemble。

注意：

- UE DCC Export **不能**用旧的 DHI CharacterImporter 直接装，必须用 MetaHuman for Maya。
- 不要同时开两个 Maya：调试端口会冲突，第二个窗口可能卡住。

### 2. 检测当前角色 / 标准化

- 标准 MetaHuman 场景：检测通过后即可导出。
- 自定义角色：检测失败时会询问是否 **标准化**。标准化 **不改** 原控制器和骨骼名；会为面部面板创建隐藏的 `CTRL_*` 代理，供 Max Morph 接线。网格名映射写入场景元数据。

### 3. 导出至 3ds Max

会做这些事：

1. 把全部面部滑杆归零，再烘焙 Morph（脸、牙、唾液/牙龈、眼睛等相关网格）。
2. 二维控制器（嘴、下巴、眼睛等）额外烘焙角落残差 Morph，Max 里用双线性权重接线。
3. 导出 FBX（文件保持 Maya 的 Y 向上）。
4. 启动 3ds Max，运行装配脚本：导入 FBX（转到 Z 向上）、导入 Morph OBJ、接线、限位、保存归档。

导出后请在 Max 里确认角色是 **直立** 的。装配日志里会有一行 `fbx Z-up probe ... (standing: Z > Y)`，站立时高度应在 Z 轴。

**改过轴向或 Morph 逻辑后，必须从 Maya 重新点一次「导出至 3ds Max」**，不要沿用旧 FBX / 旧 `.max`。

### 4. 其他菜单

| 菜单项 | 作用 |
|--------|------|
| 导入 MH | 导入 UE DCC Export 并装配 |
| 检测当前角色 | 检查场景；必要时标准化 |
| 导出至 3ds Max | 烘焙 Morph、导出 FBX、启动 Max 装配 |
| UE5 控制器同步 | 打开 Maya → UE Control Rig 同步面板（需本机有对应工程脚本） |
| 显示控制器 / 隐藏控制器 | 显示或隐藏场景里的身体与面部控制器 |
| 检查更新 | 查询 GitHub Releases 是否有新版本 |

---

## 导出到 Max 时的轴向（1.3.31）

| 软件 | 向上轴 |
|------|--------|
| Maya | Y 向上 |
| 3ds Max | Z 向上 |

做法：

- Maya 导出 FBX 时标明 **Y 向上**，并且 **不再** 在 Maya 里先转成 Z 向上（否则 Max 会再转一次，角色会转两次）。
- Max 导入时打开轴转换，目标为 **Z 向上**。FBX 会对每个根节点转 90°，子级的网格、骨骼、控制器、IK、蒙皮一起跟着转。
- 面部 Morph 的 OBJ 仍按原来的 **绕 X 轴转 -90°** 对齐同一套 Z 向上空间。

不要在 Maya 里手动把角色先转成 Z 向上再导出。

---

## Max 场景归档

一键导出不会只写一个 `_face_rigged.max`，而是按 Max 版本归档：

- 当前 Max 年份：`{角色}_face_rigged_max{年}.max`（例如 `_max2026.max`）
- 若当前 Max 高于 2024：额外尝试保存 `_max2024.max`（失败则只保留当前版）
- 若当前就是 2024：只写一份 `_max2024.max`

Max 2026 另存为 2024 前，会自动对齐颜色管理相关默认值，避免弹窗打断。

---

## 仓库结构

```text
mh2max/
├── install.bat               一键安装
├── tools/                    安装脚本
├── vendor/                   MetaHuman for Maya 压缩包（从 Release 下载）
├── plug-ins/mh2max.py        Maya 插件入口
├── scripts/mh2max/           Maya 端 Python（导入 / 导出 / 检测 / 菜单）
├── max/mh2max_pipeline.ms    Max 一键装配
├── mh2max.mod.example        Maya 模块模板
├── userSetup.example.py      延迟加载菜单示例
├── reload_menu.py            不关 Maya 时重载菜单
├── 说明.txt                  中文使用说明（与本文相同用途）
├── 更新日志.txt
└── README.md                 本说明（GitHub 首页）
```

---

## 已知限制

- Max 里多控制器叠加是线性 Morph 近似，和 Maya RigLogic 的非线性组合会有少量差别。
- 纯法线/贴图驱动的皱纹（几何顶点几乎不动）不会做成 Morph。
- 路径含中文时，部分导入步骤会改走 `%LOCALAPPDATA%\mh2max\stage\` 英文临时目录。
- 身体控制器目前 **不** 在 Max 里重建 Maya 约束/IK；身体姿势以 FBX 带进来的层级为准。面部走 Morph。
- 「UE5 控制器同步」依赖本机 MeshToMetahuman 工程里的脚本；没有该工程时该菜单会提示找不到文件。

---

## 许可

本工具为管线开源发布。MetaHuman、Epic 的商标与资产须遵守 Epic 相关许可。详见 [LICENSE](LICENSE)。
