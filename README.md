# 人格演出工作台

适用于 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher) 的《边狱巴士》(Limbus Company) 人格外观随机插件。
通过 WarpHook 注入原生 DLL，在战斗中替换罪人外观、随机切换人格，并按原生触发条件播放 Boss 语音与气泡。

当前源码版本 **1.0.1** · 协议 75 · 原生模块 `SinnersNative-v64.dll` · 适用启动器 `0.8.9-release.fix.4`

1.0.1 的新单位检测会显示进度，并从本地游戏缓存读取章节与封面。“添加人格”默认显示整个目录，可按角色、敌方单位、异想体或章节筛选。覆盖外观缺少指定攻击槽时，优先播放该外观已有的攻击动作。缺少专属攻击时间线时，当前外观通过短促位移表现攻击。

---

## 安装

全新安装时，在 FaustLauncher 中选择“从本地安装”，导入下表中的启动器安装包。已安装 1.0.0 的用户也可以在工作台中选择“检查并更新”。

| 文件 | 说明 |
| --- | --- |
| [启动器完整安装包（通用 ZIP）](https://github.com/Chrismick111/faust-random-identity/releases/download/v1.0.1/FaustRandomIdentity-Launcher-Deflate.zip) | 推荐全新安装，内含启动器识别用的中文插件目录 |
| [启动器完整安装包（小体积）](https://github.com/Chrismick111/faust-random-identity/releases/download/v1.0.1/FaustRandomIdentity-Launcher.zip) | 相同内容，使用 LZMA 压缩 |
| [工作台更新包](https://github.com/Chrismick111/faust-random-identity/releases/download/v1.0.1/FaustRandomIdentity-WarpHook.zip) | 工作台自动下载使用，文件位于压缩包根目录 |
| [默认图像包](https://github.com/Chrismick111/faust-random-identity/releases/download/v0.79.1/FaustRandomIdentity-Portraits.zip) | 可选，623 张图片，覆盖 693 个外观条目，工作台也可单独下载 |

手动安装时，把启动器完整安装包解压到 `FaustLauncher/addons/`。确认目录结构如下。可选图像包解压到 `人格演出工作台/` 内。

```
FaustLauncher/addons/人格演出工作台/
  addon_info.json
  compatibility.json
  scr.py
  Assets/
  Workbench/
    portraits/          <- 来自立绘包
```

也可以只装核心包，之后在插件里点「下载默认头像」自动补齐。1.0.1 只通过 WarpHook 加载原生模块。若 WarpHook 返回错误 87，插件会在日志中保留原因并停止本次游戏的加载。

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
5. `Workbench/portrait_source.json` 必须列入 `package_files`，其 `url` / `sha256` 与实际头像包一致
6. 不得包含 `native_pools.bin`、`随机设置.json`、`自定义人格池.json`、`animation-times-*`、`*.log`、`*.bak*`

```powershell
python Workbench/package_release.py --addon . --output C:\temp\FaustRandomIdentity-WarpHook.zip
```

输出路径须在插件目录外且原先不存在。

向 FaustLauncher 的“从本地安装”提供 ZIP 时，加上 `--launcher`。启动器用包含 `addon_info.json` 的文件夹名登记插件，包内路径应为 `人格演出工作台/addon_info.json`。工作台在线更新继续使用清单位于包根目录的标准包。

> 注意：`release_compatibility.py` 加载时对 `addon_info.json` 只校验版本、跳过哈希（启动器安装时会改写名称与说明），
> 但 `github_update.py` 的安装校验 **仍会比对它的包内哈希**。两边都要满足，改版本号后记得同步 `package_files`。

---

## 致谢

插件由原「全角色随机人格」模组演进。启动器为 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher)。
现有元数据列出的作者为神必六角恐龙。第三方代码与资源的许可由各自权利人决定。

## 许可证

本项目拟采用 GPL-3.0，完整条款见 [LICENSE](LICENSE)。
原模组及其他第三方部分的授权与兼容性仍待核实。
