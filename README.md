# mh2max (Alpha)

MetaHuman 面部一键导出与 3ds Max 装配管线：**Maya 导入 → Morph 烘焙 → FBX → Max Morpher 接线**。

> **Alpha 版本**：API 与行为可能变更；请在测试项目中验证后再用于生产。

**当前版本：1.3.3** · 目标环境：Maya 2022+ / 3ds Max 2022+（开发测试：Maya 2026 + Max 2026）

## 一键安装（推荐）

1. 克隆或解压本仓库到任意路径（支持中文路径）
2. 从 [Releases](https://github.com/Elijah-Neverdie/mh2max/releases) 下载 `MetaHumanForMaya-1.3.1-win64.zip` → 放入 `vendor/`
3. 双击 **`install.bat`**
   - 扫描 Maya / Max 版本，默认全部安装
   - 未检测到时支持粘贴 `.lnk` 快捷方式（多层嵌套）或 exe 路径
   - 多 Max 版本时可选择默认导出版本
   - 配置写入 `%LOCALAPPDATA%\mh2max\config.json`

## 功能

- **导入 MH**：解压 UE 5.6+ DCC Export zip，通过 MetaHuman for Maya 自动装配
- **导出至 3ds Max**：限位、单轴 + 角落 combo 残差 Morph、FBX、启动 Max 自动装配
- **Max 归档**：`{角色}_face_rigged_max{年}.max`，Max > 2024 时额外尝试 `_max2024.max`

## 外部依赖（需自行安装，不含在本仓库）

| 依赖 | 用途 | 必需场景 |
|------|------|----------|
| **Autodesk Maya** 2022+ | 导入 / 导出 / Morph 烘焙 | 始终 |
| **Autodesk 3ds Max** 2022+ | 导入 FBX、Morpher 装配 | 一键导出至 Max |
| **[MetaHuman for Maya](https://www.fab.com/listings/9e3bf55e-d4c3-44fc-a3d4-ec4cb772ec29)**（Epic / Fab） | UE zip 的 Character Assembler + RigLogic | 「导入 MH」 |
| **MetaHuman 角色包** | DCC Export zip 或已装配 `.mb` | 业务数据 |
| **Quixel DHI / MSLiveLink**（可选） | 旧版 SourceAssets 自动装配 | 仅 legacy DHI，非 UE 5.8 zip |

本仓库 Git 内**不含**约 1.5GB 的 MetaHumanForMaya 压缩包；请从 **Releases** 下载。`.mod` 参考文件见 `vendor/MetaHumanForMaya.mod`。

Maya 侧无 pip 依赖；Max 侧使用内置 Morpher / FBX / OBJ，Windows .NET Timer。

## 安装（手动）

1. 克隆本仓库到任意路径，例如 `D:\Tools\mh2max`
2. 复制模块描述文件：

   ```text
   copy mh2max.mod.example → %USERPROFILE%\Documents\maya\modules\mh2max.mod
   ```

   编辑 `mh2max.mod`，将第二行的路径改为**本机仓库绝对路径**。

3. （推荐）在 `Documents\maya\scripts\userSetup.py` 中加入 `userSetup.example.py` 中的延迟菜单加载代码；或每次在脚本编辑器运行 `reload_menu.py`。
4. 安装 **MetaHuman for Maya** 到 `Documents\maya\modules\MetaHumanForMaya`（见 Epic 文档）。
5. 重启 Maya → 菜单 **MH2Max** 或 Epic **MetaHuman** 下出现：导入 MH / 导出至 3ds Max / 检测。

可选环境变量：

- `MH2MAX_EXE` — 指定 `3dsmax.exe` 路径
- `MH2MAX_DHI_ROOT` / `DHI_ROOT` — legacy DHI 根目录

## 菜单

| 项 | 说明 |
|----|------|
| 导入 MH | UE DCC Export zip → 解压 + 自动装配 |
| 导出至 3ds Max | Morph + FBX + 启动 Max 装配 |
| 检测当前角色 | 检查场景中 MetaHuman 节点 |

## 仓库结构

```text
mh2max/
├── install.bat               # 一键安装（Maya 模块 + MetaHuman + Max 配置）
├── tools/                    # 安装脚本 / 快捷方式解析
├── vendor/                   # MetaHumanForMaya zip（Release 下载）
├── plug-ins/mh2max.py
├── scripts/mh2max/           # Python 包（导入 / 导出 / 检测）
├── max/mh2max_pipeline.ms    # Max 一键装配脚本
├── mh2max.mod.example        # Maya 模块模板
├── userSetup.example.py      # 菜单自动加载示例
├── reload_menu.py            # 手动重载菜单
├── 说明.txt / 更新日志.txt
└── README.md
```

## 已知限制（Alpha）

- RigLogic 多控制器组合在 Max 为线性 Morph 近似
- 部分皱纹控制（如法线驱动）无几何 Morph
- 路径含中文时导入会使用 `%LOCALAPPDATA%\mh2max\stage\` 临时英文目录
- Max 2026 down-save 2024 依赖颜色管理设置对齐（见更新日志）

## 许可

本工具为作者自用管线开源发布；MetaHuman、Epic 商标与资产使用须遵守 Epic 相关许可。详见 [LICENSE](LICENSE)。
