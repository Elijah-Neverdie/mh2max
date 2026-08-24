MetaHumanForMaya (Epic Games)
=============================

本目录用于存放 **MetaHuman for Maya** 离线安装包（不由 mh2max 开发，版权归 Epic Games 所有）。

## 文件

| 文件 | 说明 |
|------|------|
| `MetaHumanForMaya-1.3.1-win64.zip` | 从本机 Epic 安装包打包（含 `MetaHumanForMaya/` + `MetaHumanForMaya.mod`） |
| （GitHub Release 附件） | 因体积约 1.5GB，**不进入 Git 仓库**，请从 [Releases](https://github.com/Elijah-Neverdie/mh2max/releases) 下载 |

## 安装

1. 将 zip 放入本目录 `vendor/`
2. 双击仓库根目录 **`install.bat`**
3. 默认会安装 mh2max 模块 + 解压 MetaHumanForMaya 到 `%USERPROFILE%\Documents\maya\modules\`

## 许可

MetaHuman、MetaHuman for Maya 及相关库受 **Epic Games 最终用户许可** 约束。  
分发此 zip 仅为方便 mh2max 用户部署；请确保你有权使用 Epic 提供的 MetaHuman 工具链。

官方获取途径：[Fab - MetaHuman for Maya](https://www.fab.com/listings/9e3bf55e-d4c3-44fc-a3d4-ec4cb772ec29)

## 支持版本（本包 1.3.1）

- Maya **2024 / 2025 / 2026 / 2027**（Windows x64）
- mh2max 管线额外支持 Maya **2022+**（无 MetaHuman 插件时仅 DHI 旧流程）
