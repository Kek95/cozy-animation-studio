# Cozy Animation Studio · 治愈动画工作室

一个**独立于生成平台**的动画制作 Skill：将一句画面想法或生活经历扩写为剧本，经参考图、镜头生成、审片与剪辑交付短片。支持每集一个故事的系列策划与连续性记录；可直接连接图片/视频 API，也可使用现有生成工具或 ComfyUI。

**不需要安装或运行 ComfyUI。**它只是可选适配器之一；图片、视频、配音和音乐可以分别选择不同服务。

```text
画面想法 → 剧本扩写 → 主题清单 → 分镜
        → 角色与场景参考图 → 镜头图片 → 视频生成
        → 筛选与局部重做 → 剪辑配音 → 成片
                          │
                   可替换的生成服务
                ┌─────────┼─────────┐
             直接 API   现有工具/SDK   ComfyUI
```

默认制作**每条90–120秒的治愈解压生活短片**，提供宫崎骏／吉卜力式二维手绘动画风格预设，也可以替换。项目与上述创作者、工作室及模型供应商无隶属关系。

默认加入连续轻配乐和环境/动作音，无解说旁白，必要对白少量使用；可按要求改为纯环境音或静音。重点是**动作连贯、风格统一、故事丰满**：动作有起势、接触与结果，前后镜继承实际状态；共享已通过的角色/场景与风格锚点；用相连的生活过程、细微互动和满足的收尾展开情绪。新项目缺少必需配乐时会阻止最终合成；配乐需由可用服务生成或提供真实素材。

## 后续视频的默认制作标准

- **更多有效画面**：90–120秒约26–36个独立构图，105秒从30镜左右起稿；环境、行动、接触细节和人物反应交替，不用同一图反复推近充镜数。
- **正常动作、利落剪辑**：多数剪辑段约2–4秒；从实际源片剪掉起手等待、无意义尾停与重复执行，保留接触和释放。动作/反应切为主，连续音乐与环境声连接画面。
- **有人居住的生活圈**：主空间周边有其他房屋、邻居或路人自然做事；先锁定建筑关系、配角身份和比例，少量真实互动体现惬意。明确的独处/室内要求覆盖此预设。
- **完整生活故事**：每集仍有一个愿望、相连行动和满足收尾，不以密集碎片或无关街景代替叙事。

这些是创作与审片默认值，沿用用户已选择的服务、模型和限制；不启动任何付费生成，也不自动重制既有成片。详见[动作与剪辑](references/motion-and-sound.md)、[生活圈美术](references/art-direction.md)及[故事与32镜示例](references/series-production.md)。

## 示例用法

安装后在 Codex 中输入：

> 使用 $cozy-animation-studio：雨停后把借来的伞送还邻居，路过有人推车的小巷，带回两枝薄荷放在窗边。做成90–120秒、16:9的治愈解压手绘动画，构图丰富、切镜利落、正常动作速度，其他房屋和配角与主线自然相连。视频直接调用我的Seedance API；先按真实接口文档配置接入。

也可以选 ComfyUI 或混合使用：

> 生图用我配置的图片 API，视频使用 ComfyUI 中已打开的图生视频工作流，配音使用现有 TTS 服务。

修改已有项目：

> 继续上次项目，只重做 S03：女孩搅汤的手部不自然。保留已通过的角色、场景和其他镜头。

开发治愈生活系列：

> 使用 $cozy-animation-studio：围绕窗边阅读、雨天烘焙、整理花草和宠物陪伴，每集90–120秒。先列主题清单和故事卡，再写第一集的完整剧本、分镜及声音方案；暂不生成素材。

默认每集90–120秒，目标105秒，30秒仅作显式短片或动作小样。故事可以轻，以愿望、准备、执行、细微互动和可见结果积累情绪，不强加冲突，也不靠重复镜头或慢放填时长。内附[系列示例](assets/series-example.json)、[105秒32镜邻里生活制作计划](assets/cozy-episode-project.example.json)和[系列指南](references/series-production.md)。示例均未生成素材，规划路径为空，不代表已有成片。

中国农村记忆保留为用户可主动选择的扩展题材，见[农村系列示例](assets/rural-series-example.json)和[农村单集示例](assets/rural-episode-project.example.json)，不会自动注入新的治愈项目。

系列、故事与审美检查由Codex实际维护；现有CLI管理单集项目与素材，不包含自动验剧本、自动风格评分、跨集调度或唇形同步系统。

## 核心与适配器

| 层级 | 职责 | 是否依赖 ComfyUI |
|---|---|---|
| 制作流程 | 剧本、主题、分镜、风格、审片、局部重做 | 否 |
| 项目记录 | 候选、任务状态、provider、素材与选片 | 否 |
| 剪辑工具 | FFmpeg 裁切、合成、配音/音乐混合、技术检查 | 否 |
| JSON HTTP 适配器 | 按真实接口配置提交、查询和下载产物 | 否 |
| 外部素材导入 | 接受其他工具、SDK 或人工生成的媒体文件 | 否 |
| ComfyUI 适配器 | 节点模板、参数绑定、既有任务收集 | 仅选用此路线时 |

Skill 由 Codex 执行创作与协调，生成模型由所选服务提供。它不是模型权重，也不包含常驻后台调度服务。

## 环境要求

- 支持本地 Skills 和工具执行的 Codex 环境。
- Python **3.10+**；运行脚本只使用标准库。
- `ffmpeg`、`ffprobe` 位于 PATH，用于剪辑、抽帧和技术检查。
- 生成时至少有可用的图片/视频服务、工具，或已有素材。模型权限、账户和费用取决于所选服务。
- 只有选择 ComfyUI 路线时，才需要 ComfyUI 及相关节点。

## 安装

下载或克隆本仓库，在仓库根目录运行：

```bash
python3 scripts/install.py
```

默认安装到 `${CODEX_HOME}/skills/cozy-animation-studio`；未设置 `CODEX_HOME` 时使用 `~/.codex/skills/cozy-animation-studio`。现有同名技能不会被覆盖。

```bash
# 先查看安装位置，不写文件
python3 scripts/install.py --dry-run

# 更新已有版本，旧版本会保留为备份
python3 scripts/install.py --replace
```

支持 `--dest /path/to/skills/cozy-animation-studio`。安装后新建 Codex 聊天，使用 `$cozy-animation-studio`。

## 直接连接视频 API

随附的 [JSON HTTP 配置示例](assets/providers/json-http.example.json) 支持“JSON POST 提交 → JSON GET 查询 → URL 下载”的异步 API。**示例地址和字段是假设协议，必须按你所用平台的真实文档修改；不是某一家 Seedance 平台的已验证请求格式。**

1. 将配置复制到工作目录，填写真实 base URL、提交/查询路径、状态和产物字段映射。
2. 在本地环境设置配置引用的 `VIDEO_API_KEY`；不要把密钥写入 JSON 或 GitHub。
3. 按该平台文档创建请求 JSON，包含真实模型名、提示词和图像条件参数。
4. 由 Skill 调用下列命令，预览后按已有制作授权提交。

```bash
# 初始化项目，再由 Codex 写好 project.json 的剧本和分镜
python3 scripts/studio.py init work/film01 \
  --idea '傍晚窗边泡茶，与猫一起阅读' --ratio 16:9
python3 scripts/studio.py validate work/film01

# 默认仅预览，不联网、不提交
python3 scripts/studio.py submit work/film01 --shot S01 --candidate v1 \
  --provider work/video-provider.json --request work/S01-request.json

# 实际提交：可能产生所选服务的费用
python3 scripts/studio.py submit work/film01 --shot S01 --candidate v1 \
  --provider work/video-provider.json --request work/S01-request.json --execute

# 查询原任务并下载结果，不重新生成
python3 scripts/studio.py collect work/film01 --provider work/video-provider.json
```

接入细节、状态映射、超时恢复、图片输入和扩展边界见 [服务接入指南](references/providers.md)。需要签名、multipart 上传、SDK 或特殊响应时，使用该服务的工具/专用适配器，并通过 `studio.py import` 接入产物；不声称通用 JSON 配置支持所有 API。

## 可选 ComfyUI 接入

选择这条路线后阅读 [ComfyUI 指南](references/comfyui.md)。节点检查和三个 API 图模板分别位于 `scripts/workflow.py` 与 `assets/comfyui/`；它们不会参与直接 API 的提交路径。

```bash
python3 scripts/workflow.py doctor --server http://127.0.0.1:8188
python3 scripts/studio.py collect work/film01 --server http://127.0.0.1:8188
```

ComfyUI 提交使用已配置的 UI/正式 API，随后登记真实任务 ID。旧版本项目的 `prompt_id` 仍可读取。

## 文档

- [Skill 入口](SKILL.md)：完整制作流程与服务选择。
- [美术指导](references/art-direction.md)：风格、角色、场景和镜头提示词。
- [动作与声音](references/motion-and-sound.md)：动作编排、流畅度检查、连续配乐与最终听检。
- [单元故事系列](references/series-production.md)：系列设定、分集故事卡、叙事检查与归档。
- [2000年代中国农村设定](references/rural-china-2000s.md)：地域、年代、原创补写与资料边界。
- [制作指南](references/production.md)：项目记录、审片、重做与剪辑。
- [服务接入](references/providers.md)：直接 API、外部工具与适配器约定。
- [ComfyUI 可选接入](references/comfyui.md)：节点工作流路线。

## 细节与连续性检查

本版默认90–120秒（CLI目标105秒）。为水龙头、杯/壶、手指、桌面落点等接触动作扩写前置状态、左右手分工、几何净空、先后顺序和释放条件。动作采用正常生活速度，按真实动作估时，保留自然反应并裁掉多余等待。每个固定空间绑定布局版本，逐镜传递门窗、灯、道具位置与液位。

完整规则和水龙头示例见 [镜头契约](references/shot-contracts.md)。视频生成前执行：

```bash
python3 scripts/studio.py preflight /path/to/project
```

检查覆盖动作时间预算、布局版本、相邻镜道具状态交接与允许变化；需要先为镜头补齐契约。它不识别实际画面碰撞，也不承诺任何模型不出错。真实产物仍须按正常速度、密集帧和精确切点检查，失败时仅重做受影响镜头。

## 验证状态与限制

- 自动化测试覆盖独立 API 提交/查询/下载、提交中断保护、多服务记录、外部素材导入、安装、工作流绑定、选片和媒体合成。
- 测试使用模拟 API 与本地生成的媒体，不调用付费模型。真实网关仍需按文档适配并做小样验收。
- ComfyUI 图片/图生视频模板完成节点 schema 核对，尚未进行付费端到端渲染验收。
- 直接 API 提交默认预览；`--execute` 才调用 POST。记录在提交前落盘，结果不确定时禁止自动重试。
- 候选上限在内置提交前检查，预算金额仍由 Codex 按供应商报价与用户授权控制，不是支付限额系统。
- 同一项目应串行修改；不提供跨进程锁。相同 seed 也不保证角色一致或跨服务复现。
- 语音/音乐生成使用外部服务；剪辑工具自动读取项目音轨路径，负责对齐与混音。缺配乐检查只检查配置与媒体可用性，不能代替实际听检；提高导出帧率也不等于运动插帧。

## 开发与测试

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_skill.py
python3 -m unittest discover -s tests -v
```

FFmpeg 未安装时媒体测试会跳过，其他测试照常运行。GitHub Actions 安装 FFmpeg 后执行完整测试。

```text
SKILL.md                  独立制作流程
assets/project-example.json
assets/series-example.json 治愈生活系列与故事卡示例
assets/cozy-episode-project.example.json  105秒32镜邻里生活与连续性计划
assets/rural-series-example.json  可选农村题材系列
assets/rural-episode-project.example.json  旧版180秒示例，仅显式选择长片时使用
assets/providers/         直接 API / ComfyUI 配置示例
assets/comfyui/            可选节点工作流与绑定表
references/               美术、制作与服务接入指南
scripts/studio.py         平台无关项目与任务操作
scripts/providers.py      生成服务适配器
scripts/edit.py           本地剪辑与审片工具
scripts/workflow.py       可选 ComfyUI 节点工具
scripts/install.py        安装器
scripts/validate_skill.py 包结构验证
tests/                    无付费调用的自动化测试
```

## License

代码和文档采用 [MIT License](LICENSE)。模型、服务及用户参考素材遵守各自条款。本仓库不含模型权重、API 密钥或参考视频素材。
