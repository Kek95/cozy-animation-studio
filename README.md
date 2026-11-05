# Cozy Animation Studio · 治愈动画工作室

一个**独立于生成平台**的动画制作 Skill：将一句画面想法扩写为剧本，经参考图、镜头生成、审片与剪辑交付短片。可直接连接图片/视频 API，也可使用现有生成工具或 ComfyUI。

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

默认提供宫崎骏／吉卜力式二维手绘田园动画风格预设，也可以替换。项目与上述创作者、工作室及模型供应商无隶属关系。

## 示例用法

安装后在 Codex 中输入：

> 使用 $cozy-animation-studio：夏日傍晚，女孩在花园摘番茄，给奶奶做晚饭。做成 30 秒、16:9 的治愈动画。视频直接调用我的 Seedance API，不使用 ComfyUI；先按我提供的接口文档配置接入。

也可以选 ComfyUI 或混合使用：

> 生图用我配置的图片 API，视频使用 ComfyUI 中已打开的图生视频工作流，配音使用现有 TTS 服务。

修改已有项目：

> 继续上次项目，只重做 S03：女孩搅汤的手部不自然。保留已通过的角色、场景和其他镜头。

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
  --idea '女孩在雨天的小屋里做早餐' --duration 30 --ratio 16:9
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
- [制作指南](references/production.md)：项目记录、审片、重做与剪辑。
- [服务接入](references/providers.md)：直接 API、外部工具与适配器约定。
- [ComfyUI 可选接入](references/comfyui.md)：节点工作流路线。

## 验证状态与限制

- 自动化测试覆盖独立 API 提交/查询/下载、提交中断保护、多服务记录、外部素材导入、安装、工作流绑定、选片和媒体合成。
- 测试使用模拟 API 与本地生成的媒体，不调用付费模型。真实网关仍需按文档适配并做小样验收。
- ComfyUI 图片/图生视频模板完成节点 schema 核对，尚未进行付费端到端渲染验收。
- 直接 API 提交默认预览；`--execute` 才调用 POST。记录在提交前落盘，结果不确定时禁止自动重试。
- 候选上限在内置提交前检查，预算金额仍由 Codex 按供应商报价与用户授权控制，不是支付限额系统。
- 同一项目应串行修改；不提供跨进程锁。相同 seed 也不保证角色一致或跨服务复现。
- 语音/音乐生成使用外部服务；剪辑工具负责对齐与混音。

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
