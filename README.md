# 全角色随机人格 WarpHook

适用于 FaustLauncher 的《边狱巴士》外观随机插件源码快照，基于 v0.63 候选版整理。

## 目录

- `native/`：原生运行时 C 源码和测试。
- `addon/`：启动器加载逻辑、设置工具与工作台源码。

该快照不含游戏资源、人物图片、已编译插件、用户配置或日志，因此不能直接作为启动器安装包使用。编译需要 Windows x64、Zig、MinHook 及对应版本的 FaustLauncher 和游戏；现有代码依赖游戏版本的 IL2CPP 接口映射，游戏更新后需要重新适配。此仓库尚未提供完整的自动构建和资源生成流程。

## 当前进度

支持自定义外观池、随机切换、战斗开始时优先准备外观和设置工作台。神父的死亡语音与气泡已经过游戏内测试。v0.63 增加 1337 的死亡语音候选，尚未实机验证。其他 Boss 的语音条件和开场语音仍在调查，不能认为全部 Boss 已支持；实际演出取决于资源准备和游戏状态。

## GitHub 更新与发布

工作台的“检查并更新”从本仓库的最新正式 GitHub Release 检查版本；它不使用 main 分支的源码当作安装包。发布者需从一个已校验的完整插件目录生成安装包，并把文件名为 `FaustRandomIdentity-WarpHook.zip` 的文件上传为 Release 资产。Release 标签需使用 `v主版本.次版本.修订号`，并高于用户已安装的版本；GitHub 需提供该资产的 SHA-256 摘要。

在包含 `Workbench/package_release.py` 和 `Workbench/github_update.py` 的完整插件目录中，执行：

```powershell
python Workbench/package_release.py --addon . --output C:\temp\FaustRandomIdentity-WarpHook.zip
```

输出路径须在插件目录外且原先不存在。脚本校验兼容清单并排除用户设置，规范化目录权重；图片及其他资源的分发授权由发布者确认。更新时会备份被替换文件，保留个人设置并合并本地人格目录。安装前需关闭游戏、启动器及加载器，保持独立打开的工作台运行；安装后重新启动。当前仓库尚无正式 Release 安装包。

## 致谢

插件由原“全角色随机人格”模组演进，启动器为 [FaustLauncher](https://github.com/f0lkskill/FaustLauncher)。插件现有元数据列出的作者为神必六角恐龙。第三方代码和资源的许可由各自权利人决定。

## 许可证

本项目拟采用 GPL-3.0，完整条款见 [LICENSE](LICENSE)。原模组及其他第三方部分的授权与兼容性仍待核实。
