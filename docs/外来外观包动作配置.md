# 外来外观包动作配置

导入器可读取压缩包根目录的 `mos-skin.json`，为指定 prefab 声明逐币选组、拼点、守备和 Animator 动作。清单随外观包分发，工作台验证模型资源后生成本地运行配置。没有清单的旧包继续使用自动识别。

### 私服替换包的自动识别

私服包可用 `custom_limbus_data/personality/*.json` 的 `id` 和 `appearance` 声明角色。导入器在同一模组目录中查找对应的战斗预制体，读取匹配该编号的本地化标题。多个角色按各自声明匹配。出现多个候选或缺少声明所需的模型时，工作台会指出问题。

借用原人格模型的模组可以在 `custom_motions/<appearance>/motion.bundle` 中提供指向角色姿势的动画，并在 `custom_sprites` 中提供单独的图像。导入时根据动作实际引用的身体帧绑定待机、移动、守备和攻击姿势，保留宿主的战斗与逐币时序。技能图标、立绘和特效属于不同资源。以后接入其他私服格式时，依据作者资源与动作的对应关系扩展识别，避免以特定包名或人物编号决定模型。

工作台「添加人格」列表里的「改名」可设置显示名。留空保存可恢复默认名称。自定义名称按外观编号保存在用户数据中，重导同一个外观后继续生效。

独立制作的角色可以把多个拼点片段按顺序命名，如 `KnightParry1`、`KnightParry2` 或 `KnightDuelWin1`。工作台核对名称与标准动作槽位（17 普通拼点、36 准备、37 胜利、38 失败），并检查每个片段都含可见动画且没有伤害标记。符合条件的片段连同原来的顺序写入外观。

例如导入 `Reception of the Purple Tear.zip` 后，在「添加人格 → 章节 → 外来人格」搜索 `The Purple Tear` 可找到伊织。人格声明中的 `characterId` 用于定位游戏的基础人格预载项，角色身体仍取自作者的模型。模型引用失效材质时，工作台从本机游戏资源核对名称、材质参数及着色器。还有无法确定的外部引用时，导入会报告具体资源。

### 私服运行依赖与外观素材

#### 使用游戏现有身体逐币换形

例如 `Arbiter Faust.zip` 的人格声明用迪耶奇李箱作为基础外观，技能数据为特定硬币指定另一套身体和动画片段。在工作台选择原始压缩包后，导入器按该人格自己的技能表查找普通技能、条件变体与各币的演出指令，并从玩家已下载的游戏资源生成一个外观。首次使用可能需要建立本地资源索引。界面中的 CG、头像和技能图标不作为战斗身体。

模型保留基础外观的待机、拼点和守备。攻击时，工作台使用技能标识选择作者的动作序列；其他人格佩戴时按其技能阶和硬币数匹配，依当前硬币顺序播放。私服条件技能的视觉片段可随包导入；装备外观后，伤害、硬币和状态仍由实际佩戴的人格决定。导入器使用每个技能最高已声明升阶的有效动作配置。

导入时请选择作者的外观压缩包。CustomAssetLoader 把模型放在 `custom_bundles` 中，旁边的 `asset_manifest.json` 用 `label`、`resourceId`、`bundle` 和 `assetPath` 关联资源。人格或敌人的战斗模型属于 `SD_Personality` 或 `SD_Enemy`；同一份清单也可能只登记立绘和头像。例如缪的清单登记了立绘和界面图片，战斗外观仍要从该模组的人格声明、动作包和角色贴图中读取。[CustomAssetLoader 作者说明](https://github.com/Doppelglower/CustomAssetLoader#readme)

工作台按清单中的包名和完整预制体地址加载战斗模型，支持无扩展名的 UnityFS 包。若资源编号、预制体名和地址都为全新命名，且工作台无法从游戏目录确定预加载的角色，作者可以在 `mos-skin.json` 中为该地址填写 `dependency`。

| 提供的依赖 | 从程序集元数据核对的用途 |
| --- | --- |
| `motions.dll` | 登记外观、动作和演出资源，包含动作数据与外观基础模型的读取逻辑。 |
| `ModularSkillScripts.dll` | 模块化技能、条件和效果的私服运行框架。 |
| `MTCustomScripts.dll` | 扩展被动、技能效果及战斗条件，引用 ModularSkillScripts。 |
| `SubUnitSpawner.dll` | 扩展战斗中生成子单位的逻辑，引用 ModularSkillScripts。 |

镜像幻化直接从包内数据转换外观。若某个效果只在私服运行时由脚本生成，静态读取外观包无法还原该效果。

### 随包动作配置

```json
{
  "schema": 1,
  "appearances": {
    "Assets/Example/Hero.prefab": {
      "dependency": "SD_Enemy/ExampleAppearance.prefab",
      "native_layout": "12345_ExampleAppearance",
      "plugin_version": {"min": "1.3.6"},
      "clash": {"neutral": [20, 21], "win": 32},
      "defense": {"evade": 2, "guard": 3},
      "animator": [2],
      "attack_groups": {
        "mode": "random_per_coin",
        "groups": [7, 8, 9, 24],
        "preserve_native_layout": true
      }
    }
  }
}
```

键为包内 Unity prefab 的完整资源地址，按不区分大小写的方式匹配。声明了非空 `appearances` 时，仅导入列出的预制体。每个地址都必须在包中唯一匹配，包括包内有多个模型文件的情况。`dependency` 省略时从游戏资源目录识别，填写时须使用游戏资源目录中的地址。`native_layout` 默认使用 prefab 原本的布局名，用于判断本体是否采用对应动作布局。

各项设置均可省略。使用示例时，请按实际模型的动作替换其中的槽位。

- `plugin_version` 可填写 `min`、`max` 或两者，使用三段数字版本号并包含端点。工作台在导入时读取当前插件的版本，超出范围时终止导入。
- `clash` 的键可为 `ready`、`win`、`lose`、`neutral`、`special`、`linked`，值可以是一个槽位或槽位列表。同一个槽位只能声明一次。拼点需要可播放、没有伤害标记的动作时间线。标准拼点槽位 17、23、36–38 可通过实际动画和原生槽语义确认，其他槽位需要可识别的对应动作证据。
- `defense` 可独立声明 `evade: 2`、`guard: 3`、`damaged: 4` 中的任意项。工作台核对模型上的可播放时间线、Spine 动作或 Animator 状态。`animator` 可列出要验证的槽位，要求模型的相应动作槽没有时间线，且 Animator Controller 中存在带有动画片段的 `Evade`、`Guard` 或 `Damaged` 状态。工作台也会保留自动识别的槽位。
- `attack_groups.groups` 列出该 prefab 中参与选择的攻击动作编号（7–16、24–34）。每个编号只能出现一次，并且对应完整、可识别的攻击时间线。每枚硬币从可用组中抽取一组和一个片段，并在同一硬币的重复查询期间保持结果。`preserve_native_layout` 为 `true` 时，匹配本体布局且对应动作存在的情况下优先沿用本体动作与片段。

含逐币选组的外观使用 `WBMOD2` 本地配置。只声明依赖、版本、拼点、守备或 Animator 的包仍使用 `WBMOD1`。

### 给多外观包指定语音

在需要语音的 prefab 配置中加入 `"voice": {"owner": "10916", "bank": "Example.bank"}`。`owner` 使用游戏语音事件的角色编号，`bank` 使用包中可播放的 FMOD 文件名。相应的事件或台词数据需要能识别出这个编号。含多个外观或多份 bank 的包可以为每个 prefab 分别填写。作者也可以将声音放入导入器已识别的同名配套语音包。

事件沿用该 bank 原有的游戏事件，气泡从随包的 `BattleSpeechBubbleDlg.json` 或 `Voice_*_<owner>.json` 读取。工作台找不到声明的 bank 或归属时，会让该外观继续使用原声。省略 `voice` 会沿用自动匹配。

### 旧外观迁移

保留已导入的罗兰编号和模型位置，使既有人格池和规则继续引用同一外观。完成罗兰及其他真实外观的冷启动、换皮、逐币、拼点、防御、语音和重导入验证后，再考虑移除旧文件布局。

### 合并多个模型文件

1.3.6 的导入器可在包根目录读取 `mirrorofskin-migration.json`。当基础模型和武器动作分布在多个 Unity bundle 中时，作者在 `base`、`donors` 中指定 `custom_appearance/` 内的成员文件名、SHA-256 和 prefab 名。每个供体的 `groups`、`detail`、`segments` 分别指定来源动作组、合并后的目标槽位与所需片段数。`verified_attack_details` 指定合并时检查的攻击槽位。

外来配方使用 `schema: 1`、自定的稳定 `id`、`name` 和游戏目录中存在的 `dependency`。同一 `id` 与主 prefab 名决定导入后的外观编号。随插件的 `Assets/Migrations/roland-v1.json` 给出了组映射与精灵修正的实际例子，其中 `source_archive`、`cab_namespace` 和内部资源的 `root`、`address` 专供旧外观兼容使用。外来配方省略这些字段，可另附 `mos-skin.json` 指定合并后主 prefab 的逐币选组规则。

## 随外观提供头像

在外观包根目录放置 `mos-portraits.json`，在 `mos_portraits/` 下按外观编号放置 PNG。用同名原包首次导入取得实际编号，清单只引用本包的外观。将下面的示例编号换成自己的编号。

```json
{
  "schema": 1,
  "portraits": {
    "story_WBImp_111111111111111111111111": "mos_portraits/story_WBImp_111111111111111111111111.png"
  }
}
```

每张 PNG 使用 8 位 RGB 或 RGBA，宽高各不超过 512 像素，单张最多 1 MiB。每包最多 64 张，合计不超过 16 MiB。工作台在同一次导入中保存头像和外观。玩家上传的头像优先，重置后可显示包内头像。
