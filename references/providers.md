# 生成服务与适配器

## 按能力选服务

Skill 的输入是画面想法和制作约束，输出是项目记录与成片。生成服务是可替换的执行层：图片、视频、TTS、音乐可以各用一个服务，项目不要求它们共享账户或平台。

在 `project.json` 的 `generation` 中记录各阶段选择。例如以下是说明结构，不是有效供应商配置：

```json
{
  "generation": {
    "image": {"provider_config": "config/images.json", "model": "实际图片模型"},
    "video": {"provider_config": "config/video.json", "model": "实际视频模型"},
    "speech": null,
    "music": null
  }
}
```

这些字段供 Codex 路由与追溯；CLI 使用显式 `--provider`，不会自动从阶段名称猜测服务。`null` 表示尚未选择或不需要该阶段。

接入前核对：模型标识、图生视频/多参考能力、图片上传方法、时长/比例、原生音频、鉴权、任务 ID、查询状态、下载产物及费用依据。用户明确使用第三方 Seedance 网关时，以该网关文档为准，不用官方服务或其他平台的接口代替。

## 内置 JSON HTTP 适配器

适用协议：`POST JSON` 创建异步任务，响应包含 task ID；`GET` 查询任务，JSON 包含状态和单个 URL 或 URL 数组。支持图片、视频、音频的 URL 产物；文件扩展名由配置明确给出。

从 `assets/providers/json-http.example.json` 复制并修改：

- `name`：同一服务/账户使用稳定且唯一的名字，例如 `video-main`。项目候选通过 name、kind 和 endpoint 匹配，防止不同平台相同任务 ID 串号。
- `base_url`：文档中的 API 根地址，不带密钥、query 或 fragment。
- `headers_from_env`：请求头名称映射到环境变量名和可选前缀。支持 Bearer 或平台自定义 API-key header；只在内存中读取值。
- `submit.path`、`submit.task_id_pointer`：提交路径与响应 task ID 的 JSON Pointer，如 `/data/task_id`。
- `poll.path`：包含 `{task_id}` 的查询路径；任务 ID 会 URL 编码，不直接拼接路径。
- `poll.state_pointer`、`poll.states`：实际供应商状态到 `pending/running/success/error/cancelled/unknown` 的映射。未知状态保留为 `unknown`，不能当成失败重做。
- `poll.output_urls_pointer`：JSON Pointer 指向一个 URL 字符串或字符串数组，如 `/result/videos/0/url`。尚不支持数组通配符；复杂嵌套输出需要专用适配器。
- `poll.output_extension`：实际媒体格式，例如 `.mp4` 或 `.png`。不能将图片伪装成视频。

此示例不是某家公司的真实服务合同。请求 JSON 按供应商文档编写，适配器原样发送，不猜测 `model`、`prompt`、`image_url` 等字段。

```bash
# 预览：不联网，也不要求密钥已经设置
python3 "$SKILL_DIR/scripts/studio.py" submit work/film01 \
  --shot S01 --candidate v1 --provider work/video-provider.json \
  --request work/S01-request.json

# 根据已有制作授权实际提交
python3 "$SKILL_DIR/scripts/studio.py" submit work/film01 \
  --shot S01 --candidate v1 --provider work/video-provider.json \
  --request work/S01-request.json --execute

# 每次调用只查询一次；按服务建议间隔再查，不使用紧密循环
python3 "$SKILL_DIR/scripts/studio.py" collect work/film01 \
  --provider work/video-provider.json
```

HTTP 只允许本机 loopback 服务，远程 API 使用 HTTPS。API 请求不跟随重定向，避免把凭据或付费 POST 发往另一地址。产物下载不携带 API headers，适用于公开或签名下载 URL；需鉴权的下载应使用服务专用工具，再导入文件。CLI 不打印原始响应或下载 URL，项目只保存归一化状态与本地文件路径。

## 超时、恢复与追溯

`submit` 在 POST 前登记候选为 `submitting`，返回真实 ID 后改为 `submitted`。请求异常或响应缺少 ID 时保留 `submission_unknown`。进程被终止可能留下 `submitting`，同样视为不确定，不自动重发。

先在供应商任务列表中核对本次请求。已找到任务时绑定其真实 ID：

```bash
python3 "$SKILL_DIR/scripts/studio.py" register work/film01 \
  --shot S01 --candidate v1 --provider work/video-provider.json \
  --task-id ACTUAL_TASK_ID --recover
```

确认供应商未接收任务时，由 Codex 在项目记录中写明核对依据，再将该候选标为 `error`，使用新候选版本重新提交。没有依据时保留不确定状态。恢复不修改任务、不触发生成。

如果任务已通过其他客户端提交，使用不带 `--recover` 的 `register` 登记即可。`--seconds` 是生成秒数估计，图片等非视频任务可记 0；不代表账单或成功生成时长。

## 图片、SDK 与其他工具

本地参考图必须通过所选服务支持的上传、托管 URL、base64 或文件 ID 方式实际进入图像条件字段。通用适配器不负责上传文件，也不读取提示词里的本地路径。图片和视频服务之间需要转存时，使用用户认可的存储或该平台上传入口；不擅自把素材上传到随机公共图床。

对于同步响应、multipart、base64 返回、流式响应、签名鉴权、webhook 或只能使用 SDK 的 API：优先调用已配置的相应工具/SDK；也可添加服务专用适配器。产物可统一导入：

```bash
python3 "$SKILL_DIR/scripts/studio.py" import work/film01 \
  --shot S01 --candidate sdk-v1 --file work/downloads/S01.mp4 \
  --source-label my-sdk --task-id ACTUAL_TASK_ID --seconds 5
```

没有 task ID 可省略该参数。导入会复制素材并保留来源，但不自动接受审片；仍需执行 `review`。图片、声音也可登记在各自的素材项目中。实际配音/音乐文件传给 `edit.py compose`，不强迫它们经过视频供应商。

## 添加专用适配器

当前实现位于 `scripts/providers.py`，用 `load_provider` 显式选择适配器。扩展时遵循：

```python
identity = {"name": "stable-name", "kind": "adapter-kind", "endpoint": "https://api.example.invalid"}
preflight(provider_payload) -> None         # 本地校验凭据/参数，不提交任务
submit(provider_payload) -> "real-task-id"  # 仅有需要时实现
poll(task_id, output_node=None) -> {
    "state": "success",
    "assets": [{"url": "https://download.example.invalid/result.mp4", "extension": ".mp4"}]
}
```

适配器负责供应商字段，核心只识别任务状态与素材。不同鉴权/下载协议需要专用实现；不要通过复制或修改分镜逻辑来支持新供应商。无实际端点测试时标记为“配置/模拟测试已通过”，不宣传已对接真实平台。

ComfyUI 路线见 [comfyui.md](comfyui.md)，仅在选用时需要该应用。
