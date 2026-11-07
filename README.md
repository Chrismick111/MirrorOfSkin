# 人格演出工作台

适用于 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher) 的《边狱巴士》(Limbus Company) 人格外观随机插件。
通过 WarpHook 注入原生 DLL，在战斗中替换罪人外观、随机切换人格，并按原生触发条件播放 Boss 语音与气泡。

当前版本 **0.63.2** · 协议 75 · 原生模块 `SinnersNative-v63.dll` · 测试于启动器 `0.9.5-release.fix.1`

---

## 安装

从 [Releases](https://github.com/Chrismick111/faust-random-identity/releases/latest) 下载：

| 文件 | 说明 |
| --- | --- |
| `FaustRandomIdentity-WarpHook.zip` | 插件本体（必需，约 700 KB） |
| `FaustRandomIdentity-Portraits.zip` | 默认人格立绘（推荐，约 61 MB） |

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

- `随机设置.json` — 概率、开关
- `自定义人格池.json` — 人格挑选与覆盖
- `演出编排.json` — 演出编排

### 立绘

- **默认立绘**：点「下载默认头像」，从最新 Release 拉取 `FaustRandomIdentity-Portraits.zip`，要求插件版本与 Release 一致
- **自定义立绘**：每个人格都可单独上传或重置。浏览器端缩放到 ≤384×384 转 PNG，服务端还要校验 PNG 结构与 CRC、体积 ≤1 MiB，存到 `Workbench/user_portraits/`（按人格名 SHA-256 命名），更新时受保护

---

## 更新

工作台「检查并更新」读取本仓库的 **latest 正式 Release**，不使用 main 分支源码当安装包。要求：

- 标签形如 `v0.63.2`，且高于已装版本（只比较 `主.次.修订`，后缀被忽略）
- 资产含 `FaustRandomIdentity-WarpHook.zip`，GitHub 提供 SHA-256 摘要
- 下载地址必须是本仓库的 `releases/download/`

更新会自动备份被替换的文件、保留个人设置、合并本地人格目录（保留你自己的 `weight` / `enabled`）。
**安装前请完全退出游戏与启动器**，否则会被拒绝。

---

## 当前进度

### 可用

- 自定义外观池、跨角色池、随机切换、战斗开始前置准备、概率与覆盖工作台
- 单外观模式循环映射动作，维持本体人格硬币结算时间
- NPC 援助单位入池：摩西、以斯拉、贾惜春、林黛玉、维吉里乌斯及 E.G.O. 独立外观等 14 个有 3D 模型的单位
- 神父  的死亡语音与气泡，已游戏内实测
- 默认立绘 582 张，覆盖池内 **185 / 192** 个人格（96.4%）

### 仅候选 / 未验证
- 游戏进程被检测后等待 30 秒再加载；是否消除 GC 弹窗尚待实测。
- Boss 以及援助单位的语音触发条件仍等待进一步开发，未实现所有boss以及援助单位的语音适配
- 完整战斗表现（逐硬币动作、动作时长、镜头）需在更多场景验证

### 已知限制

- 原生开场语音不可达：实测从加载到战斗开始约 206 ms，原生时间线在该窗口内已结束
- 多键歧义触发按设计保持静默——同一人格/触发条件映射到多个语音时不猜测
- 超大体型外观有概率无攻击动画

---

## 源码结构

```
addon/        启动器加载逻辑、设置工具、网页工作台
native/       原生运行时 C 源码与测试
```

本快照 **不含** 游戏资源、人物图片、已编译插件、用户配置与日志，不能直接当安装包用。
编译需要 Windows x64、Zig、MinHook；代码依赖对应游戏版本的 IL2CPP 接口映射，游戏更新后可能需要重新适配。

---

## 发布流程（维护者）

合法发布包必须满足：

1. 从**已通过校验**的完整插件目录生成
2. zip 内文件集合 **精确等于** `package_files ∪ {compatibility.json, Assets/runtime/all_sinners_pools.json}`——多一个（运行时缓存、日志、备份）或少一个都会被更新器拒绝
3. `addon_info.json` 与 `compatibility.json` 的 `version` **必须一致**，且与标签的 `主.次.修订` 匹配
4. `scr.py` 的 `DLL_NAME` 必须等于 `compatibility.json` 的 `dll`
5. 不得包含 `native_pools.bin`、`随机设置.json`、`自定义人格池.json`、`animation-times-*`、`*.log`、`*.bak*`

```powershell
python Workbench/package_release.py --addon . --output C:\temp\FaustRandomIdentity-WarpHook.zip
```

输出路径须在插件目录外且原先不存在。

> 注意：`release_compatibility.py` 加载时对 `addon_info.json` 只校验版本、跳过哈希（启动器安装时会改写名称与说明），
> 但 `github_update.py` 的安装校验 **仍会比对它的包内哈希**。两边都要满足，改版本号后记得同步 `package_files`。

---

## 致谢

插件由原「全角色随机人格」模组演进。启动器为 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher)。
现有元数据列出的作者为六角恐龙@Chrismick111。第三方代码与资源的许可由各自权利人决定。

## 许可证

本项目拟采用 GPL-3.0，完整条款见 [LICENSE](LICENSE)。
原模组及其他第三方部分的授权与兼容性仍待核实。
