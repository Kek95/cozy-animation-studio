# ComfyUI 可选接入

只有用户选择 ComfyUI 时读取本页。核心制作流程、直接 API 接入和剪辑均不依赖 ComfyUI。

## 已验证与仍需检查的边界

模板在 ComfyUI 0.44.0 环境中进行过节点 schema 检查（2026-11-05），对应节点：`ByteDance2TextToVideoNode`、`ByteDance2FirstLastFrameNode`、`ByteDance2ReferenceNodeV2`、`OpenAIGPTImage1`、`OpenAIGPTImageNodeV2`、`LoadImage`、`SaveImage`、`SaveVideo`。节点与模型选项会随安装版本变化。开始新项目时运行 doctor，确认当前环境具有相应能力。

任务收集和剪辑工具已使用实际生成片段验证；图片/图生视频模板完成了节点 schema 校验，尚未进行付费端到端渲染测试。自动化测试不代表模型输出画风已经通过验收。

## 三条可组合路线

1. **风格图、角色图、场景图**：文本 → 图像生成 → SaveImage。可优先使用用户提供的图像工作流。随附 `assets/comfyui/image_generate_api.json` 是已核对的 GPT Image 节点的基本模板。
2. **镜头图**：固定参考图片 → 图像编辑/参考生成 → SaveImage。随附 `assets/comfyui/image_reference_api.json` 接一张参考图；需要多参考时使用实际的多参考图节点/工作流，或已支持参考输入的图像工具，不声称一张图锁住全部角色与场景。优先保留用户既有模型和参考输入方式。
3. **镜头视频**：LoadImage(该镜的单张关键帧) → ByteDance2FirstLastFrameNode(Seedance 2.0) → SaveVideo。随附 `assets/comfyui/seedance20_i2v_api.json` 只使用首帧。需要同时绑定多张角色/场景图时改用经实际检查和导出的 Reference 节点，不猜自动增长输入字段名。

纯文生视频节点通常没有参考图入口。完整流程需要配套的图片与图生视频工作流，参考图片必须连接到节点的图像输入。

第三方平台或自建网关应使用该平台的实际 ComfyUI 节点、接口文档和导出图；随附 Partner 模板不是所有 Seedance API 通用的请求格式。保留用户已经配置的接入方式，不自动切换供应商。

## 实际参数与能力检查

```bash
python3 "$SKILL_DIR/scripts/workflow.py" doctor --server http://127.0.0.1:8188 --out work/comfy-capabilities.json
```

所附模板中的 Seedance 2.0 动态参数在导出 API 图中使用 `model.prompt`、`model.duration`、`model.resolution`、`model.ratio`、`model.generate_audio`。模型选择以 `inputs.model` 为准，工作流文件名和节点显示标题可能含 2.5，但实际选中的是 2.0。不要因标题含 2.5 而切换模型。

首帧节点使用 `first_frame: [LoadImage节点ID, 0]`。图片上传到 ComfyUI 后，LoadImage 的 `image` 值必须采用上传响应或实际 UI 给出的服务器文件名，包括可能存在的子目录，不是本机绝对路径。

`workflow.py patch` 按绑定表修改输入，保留节点链接和其他设置：

```bash
python3 "$SKILL_DIR/scripts/workflow.py" patch \
  --graph "$SKILL_DIR/assets/comfyui/seedance20_i2v_api.json" \
  --bindings "$SKILL_DIR/assets/comfyui/seedance20_i2v_bindings.json" \
  --values work/S01-values.json --out work/S01-v1-api.json
```

`S01-values.json` 包含本镜实际值，例如 `prompt`、`image`、`duration`、`resolution`、`ratio`、`seed`、`filename_prefix`。修改当前用户工作流时先导出它自己的 API 图并建立自己的绑定表；不要将模板节点 ID 套在不同图上。

## 提交、认证和产物

- UI 在本机 Comfy Desktop 中操作时，使用支持的 UI 自动化工具；按最新页面状态定位，不使用任意浏览器内部对象修改图。
- Hosted Partner 节点依赖已登录的 ComfyUI 账户及 prepaid credits。优先经已登录 UI 提交；不从浏览器存储提取认证令牌。只有用户已经配置的正式 API 认证方式存在时，才使用 API 提交。
- 提交前保存项目/镜头版本与提示词。提交后立即取得 `prompt_id`、终端保存节点 ID 并登记。只提交一次；超时先查询同一个任务。
- Hosted视频镜头默认使用独立任务记录与独立API图。一个并行图中某节点失败可能中止其他节点，导致其他云端请求已提交却没有本地产物；未经验证，不把所有付费镜头塞进同一张图。批次中止后逐节点核对，不能把没有文件当成未提交。无法取得供应商ID的请求记为结果不确定并计入请求用量；不要承诺可无损恢复或自动重跑整批。
- 服务契约：`GET /system_stats`、`GET /object_info`、`GET /queue`、`GET /history/{prompt_id}`、`GET /view?filename=...&subfolder=...&type=...`；正式任务提交为 `POST /prompt`，上传为 `POST /upload/image`（multipart）。实际执行前通过当前服务或官方资料核对提交/上传字段。
- 用户指定 ComfyUI 时，优先在 ComfyUI 完成图片与视频生成。若必需的图片编辑节点缺失，可使用用户授权的其他图片工具；明确说明路由变化，不能偷偷退回纯文生视频并宣称完成参考条件生成。
- 不将密钥、隐藏认证字段或完整用户队列写进交付文件。只导出本项目的 API 图、提示词和参数。

## 模型时长与费用

模板兼容性检查中 Seedance 2.0 的时长范围为 4–15 秒；新项目仍需核对。短于模型下限的编辑镜头可生成 4–5 秒再裁切，费用按生成时长估算。一个 15 秒多镜头生成不保证按照文字时间码精确切换；精确剪辑时使用一个镜头一段素材。

所检查的 seed 字段说明明确表示结果不保证确定性。记录它有助于追溯，不作为身份一致性的保证。

## 登记和收集

```bash
python3 "$SKILL_DIR/scripts/studio.py" register work/film01 --shot S01 --candidate v1 \
  --server http://127.0.0.1:8188 --task-id ACTUAL_TASK_ID --output-node ACTUAL_SAVE_NODE_ID
python3 "$SKILL_DIR/scripts/studio.py" collect work/film01 --server http://127.0.0.1:8188
```

也可使用 `--provider assets/providers/comfyui.example.json`。ComfyUI 适配器负责查询和收集；提交继续使用用户已配置的 UI 或正式 API。版本 1 项目的 `prompt_id` 记录仍可读取。
