# 人格演出工作台

适用于 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher) 的《边狱巴士》(Limbus Company) 人格外观随机插件。
通过 WarpHook 注入原生 DLL，在战斗中替换罪人外观、随机切换人格，并按原生触发条件播放 Boss 语音与气泡。

当前源码 **0.79.0** · 协议 75 · 原生模块 `SinnersNative-v64.dll` · 测试于启动器 `0.8.9-release.fix.4`

---

## 安装

从 [Releases](https://github.com/Chrismick111/faust-random-identity/releases/latest) 下载：

| 文件 | 说明 |
| --- | --- |
| `FaustRandomIdentity-WarpHook.zip` | 插件本体（必需） |
| `FaustRandomIdentity-Portraits.zip` | 默认人格立绘（推荐，约 64 MB） |

两个压缩包内部都是**扁平结构**（路径相对插件根目录），解压到同一个插件文件夹即可：

```
FaustLauncher/addons/人格演出工作台/
  addon_info.json
  compatibility.json
  scr.py
  Assets/
  Workbench/
    portraits/          <- 来自立绘包
```

也可以只装核心包，之后在插件里点「下载默认头像」自动补齐。

**依赖**：Windows x64、FaustLauncher、WarpHook。工作台优先使用启动器自带的 `resources/mod_loader/_internal/venv` 里的 Python；
该路径不存在时才回退到系统 Python，此时需要 3.9 或更新版本。

> 立绘是分离分发的：核心包不含图片，只装核心包时人格卡片暂时没有立绘，功能不受影响。

---

## 使用

启动器托盘菜单 → 插件 → **人格演出工作台** → 打开网页端工作台。

工作台监听 `127.0.0.1` 的临时端口，每次启动生成新的随机 token 并作为 URL 前缀；只接受带 `X-Workbench` 头的请求。
启动日志在 `%TEMP%\FaustRandomIdentity-Workbench`（`workbench-start-*.log` / `workbench-error-*.log`）。

设置保存在插件目录，更新时不会被覆盖：

- `随机设置.json` — 概率、开关；`prewarm_full_pool` 默认 `false`，关闭全池预载以避免持续掉帧，需要时可手动开启
- `自定义人格池.json` — 人格挑选与覆盖
- `演出编排.json` — 演出编排

### 规则集

- 默认不启用任何随机；需要在左侧「规则集」页面点击规则集才会生效
- 支持三种范围：全局、罪人全部人格、单个人格
- 同一罪人同时只能启用一个规则集；全局规则与其它规则互斥，最后选择的优先
- 单人格规则集在创建时生成 `规则集/人格-<人格ID>.json`，未创建时不会出现
- 「填入默认全随机」会用当前罪人的默认池覆盖当前规则集内容
- 单人格规则需要配套的原生 DLL：本仓库的 `native/` 已加入按基础人格筛选池子的逻辑

### 立绘

- **默认立绘**：点「下载默认头像」，直接读取 `Workbench/portrait_source.json` 中锁定的独立直链与 SHA-256，不再查询 GitHub Release；头像包与核心版本相互独立
- **直链覆盖**：复制为 `Workbench/portrait_source.local.json` 并填写 `url` / `sha256`（可选 `size`）即可换镜像或独立地址；该文件在核心更新时受保护
- **自定义立绘**：每个人格都可单独上传或重置。浏览器端缩放到 ≤384×384 转 PNG，服务端还要校验 PNG 结构与 CRC、体积 ≤1 MiB，存到 `Workbench/user_portraits/`（按人格名 SHA-256 命名），更新时受保护

---

## 更新

工作台「检查并更新」读取本仓库的 **latest 正式 Release**，不使用 main 分支源码当安装包。要求：

- 标签形如 `v0.63.3`，且高于已装版本（只比较 `主.次.修订`，后缀被忽略）
- 资产含 `FaustRandomIdentity-WarpHook.zip`，GitHub 提供 SHA-256 摘要
- 下载地址必须是本仓库的 `releases/download/`

更新会自动备份被替换的文件、保留个人设置、合并本地人格目录（保留你自己的 `weight` / `enabled`）。
**安装前请完全退出游戏与启动器**，否则会被拒绝。

---

## 0.79.0 源码

工作台支持分章节外观池、单独启用第九章人格规则、编辑特效时间线和逐帧预览。运行插件需要对应版本的 FaustLauncher、WarpHook 和游戏客户端，玩家无需另装 LimbusArchive。

本次修复 437 个被旧配置跳过的拼点条目。动作选择区分准备、胜利和失败，也能读取位于技能槽里的专用拼点动作。语音按当前可见形态匹配，气泡跟随实际出战角色。核对的 741 个外观中，339 个有关联的角色录音事件，310 个有关联的本地化台词。这些数字是资源核对结果。

### 从源码编译

在 Windows x64 准备 Zig 和 MinHook 源码。在仓库根目录运行以下命令，把两个参数改为本机路径。

```powershell
./native/build.ps1 -Zig C:/tools/zig/zig.exe -MinHook C:/src/minhook
```

生成物为 `native/SinnersNative.dll`。`addon/` 包含启动器与网页工作台源码，完整插件安装还需要匹配的资源目录和兼容清单。安装用的 zip 见 Releases，发布页标示其独立版本。

公开版通过游戏的语言接口读取气泡。游戏本地化缺项时，如需为自己的构建加入中文备用台词，可用本机资源运行 `native/build_appearance_voice_catalog.py --help` 查看所需的索引、静态数据和语言目录。

## 发布流程（维护者）

合法发布包必须满足：

1. 从**已通过校验**的完整插件目录生成
2. zip 内文件集合 **精确等于** `package_files ∪ {compatibility.json, Assets/runtime/all_sinners_pools.json}`——多一个（运行时缓存、日志、备份）或少一个都会被更新器拒绝
3. `addon_info.json` 与 `compatibility.json` 的 `version` **必须一致**，且与标签的 `主.次.修订` 匹配
4. `scr.py` 的 `DLL_NAME` 必须等于 `compatibility.json` 的 `dll`
5. `Workbench/portrait_source.json` 必须列入 `package_files`，其 `url` / `sha256` 与实际头像包一致
6. 不得包含 `native_pools.bin`、`随机设置.json`、`自定义人格池.json`、`animation-times-*`、`*.log`、`*.bak*`

```powershell
python Workbench/package_release.py --addon . --output C:\temp\FaustRandomIdentity-WarpHook.zip
```

输出路径须在插件目录外且原先不存在。

> 注意：`release_compatibility.py` 加载时对 `addon_info.json` 只校验版本、跳过哈希（启动器安装时会改写名称与说明），
> 但 `github_update.py` 的安装校验 **仍会比对它的包内哈希**。两边都要满足，改版本号后记得同步 `package_files`。

---

## 致谢

插件由原「全角色随机人格」模组演进。启动器为 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher)。
现有元数据列出的作者为神必六角恐龙。第三方代码与资源的许可由各自权利人决定。

## 许可证

本项目拟采用 GPL-3.0，完整条款见 [LICENSE](LICENSE)。
原模组及其他第三方部分的授权与兼容性仍待核实。
