# 镜像幻化（Mirror of Skin, MOS）

适用于 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher) 的《边狱巴士》(Limbus Company) 人格外观随机插件。
通过 WarpHook 注入原生 DLL，在战斗中替换罪人外观、随机切换人格，并按原生触发条件播放 Boss 语音与气泡。

当前源码版本 **1.2.9** · 协议 75 · 原生模块 `SinnersNative-v64.dll` · 适用启动器 `0.8.9-release.fix.4`

1.2.9 新增首次使用教程、自动打开调整面板开关，并把规则集、方案、头像和游戏提取缓存迁移到启动器数据目录，插件更新不会覆盖。教程使用聚焦框和逐项悬浮提示讲解每个面板与图标按钮；“是否展示教程”完成一次后关闭，也可从右上角问号重新打开。没有特殊拼点动画素材的外观会保留游戏原生拼点，不再尝试特殊拼点姿态。工作台缺失静态时间线会恢复，卸载时会关闭工作台/扫描子进程，且不会再遍历 MOS_data 的用户数据。套皮技能动画不足时会继续从其他普通攻击组补全，不再在目标组内复读；缺少时间缓存时也会使用安全的顺序补全；补全时会优先消耗尚未使用的动画片段；同一目标组内原生索引重复时先顺序推进本组片段；技能硬币切换查看器时不重置补位计划，候补池耗尽后按候补池循环，避免锁死在一个候补组上。特殊拼点缺少精确姿态时保留游戏原生动作，并用精确定位槽修复闪避/反击错位。

---

## 安装

全新安装时，在 FaustLauncher 中选择“从本地安装”，导入下表中的启动器安装包。已安装 1.0.0 的用户也可以在工作台中选择“检查并更新”。

| 文件 | 说明 |
| --- | --- |
| [启动器完整安装包（通用 ZIP）](https://github.com/Chrismick111/faust-random-identity/releases/download/v1.2.9/FaustRandomIdentity-Launcher-Deflate.zip) | 推荐全新安装，内含启动器识别用的中文插件目录 |
| [启动器完整安装包（小体积）](https://github.com/Chrismick111/faust-random-identity/releases/download/v1.2.9/FaustRandomIdentity-Launcher.zip) | 相同内容，使用 LZMA 压缩 |
| [工作台更新包](https://github.com/Chrismick111/faust-random-identity/releases/download/v1.2.9/FaustRandomIdentity-WarpHook.zip) | 工作台自动下载使用，文件位于压缩包根目录 |
| [默认图像包](https://github.com/Chrismick111/faust-random-identity/releases/download/v0.79.1/FaustRandomIdentity-Portraits.zip) | 可选，623 张图片，覆盖 693 个外观条目，工作台也可单独下载 |

手动安装时，把启动器完整安装包解压到 `FaustLauncher/addons/`。确认目录结构如下。可选图像包解压到 `MirrorOfSkin/` 内。

```
FaustLauncher/addons/MirrorOfSkin/
  addon_info.json
  compatibility.json
  scr.py
  Assets/
  Workbench/
    portraits/          <- 来自立绘包
```

也可以只装核心包，之后在插件里点「下载默认头像」自动补齐。1.2.9 只通过 WarpHook 加载原生模块。若 WarpHook 返回错误 87，插件会在日志中保留原因并停止本次游戏的加载。

Workbench 的 Python 代码按功能拆分：

```
Workbench/
  core/    文件锁、实例控制、宿主生命周期、更新与打包
  pool/    规则集、方案、导演与池子数据
  scan/    资源扫描、单位发现、头像与章节资源
  fx/      特效方案、时间线、精灵与动作数据
  tools/   验收与发布工具
  tests/   工作台单元测试
  ui/      网页、启动脚本与使用说明
  data/    外观配对、章节、立绘源与工具数据
  workbench.py   工作台 HTTP 入口
```

原生代码目录：

```
native/
  core/    池、形态、策略与运行时基础
  clash/   拼点、硬币与章节技能映射
  voice/   语音表、语音路由与语音目录
  fx/      特效计划与播放
  story/   章节、连携、楔子与双人/三人演出
  unity/   Unity 资源读取与纹理导出
  tests/   当前原生测试，archive/ 为旧版本回归
  tools/   原生数据生成与发布工具
  data/    原生数据表
  sinners_native.c / build.ps1
```

模块目录由 `Workbench/_module_paths.py` 注入到 `sys.path`，原有扁平导入无需改动。

**依赖**：Windows x64、FaustLauncher、WarpHook。工作台优先使用启动器自带的 `resources/mod_loader/_internal/venv` 里的 Python；
该路径不存在时才回退到系统 Python，此时需要 3.9 或更新版本。

> 立绘是分离分发的：核心包不含图片，只装核心包时人格卡片暂时没有立绘，功能不受影响。

### 启动器设置与数据目录

插件设置中的「是否自动打开调整面板」控制启动时是否自动打开工作台。关闭后仍可从启动器托盘打开：**镜像幻化 → 人格、概率与演出设置**。

「是否展示教程」控制首次使用教程；教程开始前会先询问一次，跳过时还会再次确认。完成后该设置关闭，右上角问号可随时重新打开。

规则集、方案、设置、头像、扫描结果、动画时间缓存和原生池等用户数据统一保存在：

```
%APPDATA%\FaustLauncher\MOS_data
```

插件目录只保留程序和随包静态资源；升级插件时不会覆盖 MOS_data。旧版本在插件目录留下的用户数据会在首次启动时自动迁移。

---

## 使用

启动器托盘菜单 → 插件 → **镜像幻化** → 打开网页端工作台。

工作台监听 `127.0.0.1` 的临时端口，每次启动生成新的随机 token 并作为 URL 前缀；只接受带 `X-Workbench` 头的请求。
启动日志在 `%TEMP%\FaustRandomIdentity-Workbench`（`workbench-start-*.log` / `workbench-error-*.log`）。

设置保存在插件目录，更新时不会被覆盖：

- `随机设置.json` — 概率、开关；`prewarm_full_pool` 默认 `false`，关闭全池预载以避免持续掉帧，需要时可手动开启；`disable_special_clash` 默认 `true`，禁用特殊拼点动画以避免个别外观拼点时卡住，设为 `false` 可恢复
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

- **默认立绘**：点「下载默认头像」，直接读取 `Workbench/data/portrait_source.json` 中锁定的独立直链与 SHA-256，不再查询 GitHub Release；头像包与核心版本相互独立
- **直链覆盖**：复制为 `Workbench/data/portrait_source.local.json` 并填写 `url` / `sha256`（可选 `size`）即可换镜像或独立地址；该文件在核心更新时受保护
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

## 1.0.0 的本机资源与外观适配

选中外观后，特效编辑器从本机已经下载的游戏资源读取动作、时长和特效轨道，生成可复用的缓存。若某个外观缺少资源，在游戏里下载后回到编辑器点击“读取本机资源”。战斗覆盖使用的基础动作表随核心包提供。玩家无需安装 LimbusArchive。

工作台优先使用启动器已有的资源解析、纹理和音频组件。启动器的 64 位 Python 3.9 缺少组件时，工作台会从 Python 官方包仓库下载约 7.31 MB 并校验，之后复用本地副本。启动器作者只需托管上面的标准安装包。

选用对应人格并覆盖对应敌方外观时，工作台会自动应用配对适配，包括第九章父辈与子辈。楔子连携沿用原生演出，保留对应外观适配。

拼点动作区分准备、胜利和失败，也能读取位于技能槽里的专用拼点动作。语音按当前可见形态匹配，气泡跟随实际出战角色。

本版沿用 0.79.1 的独立图像包，更新插件后可以继续使用已安装的立绘。游戏兼容检查使用安装包内 `compatibility.json` 记录的文件摘要。

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
5. `Workbench/data/portrait_source.json` 必须列入 `package_files`，其 `url` / `sha256` 与实际头像包一致
6. 不得包含 `native_pools.bin`、`随机设置.json`、`自定义人格池.json`、`animation-times-*`、`*.log`、`*.bak*`

```powershell
python Workbench/core/package_release.py --addon . --output C:\temp\FaustRandomIdentity-WarpHook.zip
```

输出路径须在插件目录外且原先不存在。

向 FaustLauncher 的“从本地安装”提供 ZIP 时，加上 `--launcher`。启动器用包含 `addon_info.json` 的文件夹名登记插件，包内路径应为 `MirrorOfSkin/addon_info.json`。工作台在线更新继续使用清单位于包根目录的标准包。

> 注意：`release_compatibility.py` 加载时对 `addon_info.json` 只校验版本、跳过哈希（启动器安装时会改写名称与说明），
> 但 `github_update.py` 的安装校验 **仍会比对它的包内哈希**。两边都要满足，改版本号后记得同步 `package_files`。

---

## 致谢

插件由原「全角色随机人格」模组演进。启动器为 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher)。
现有元数据列出的作者为神必六角恐龙。第三方代码与资源的许可由各自权利人决定。

## 许可证

本项目拟采用 GPL-3.0，完整条款见 [LICENSE](LICENSE)。
原模组及其他第三方部分的授权与兼容性仍待核实。
