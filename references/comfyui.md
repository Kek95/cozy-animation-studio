# ComfyUI 可选接入

核心制作流程、直接API与剪辑不依赖ComfyUI。只有用户选择此路线才读本页，继承其已打开工作流与已配置认证。

## 当前模板与验证范围

2026-11-09在本机ComfyUI0.44.2的 `/object_info`核对了下述节点和动态字段。认可样片实际使用同类图片参考、图生视频和独立音乐路线；随包模板是脱敏最小API图，不包含认证。不同安装/版本须重新核对，不声称模板在所有机器上都已付费渲染测试。

| 用途 | 模板 | 实际入口 |
|---|---|---|
| 原创视觉基准 | `assets/comfyui/image_generate_api.json` | `OpenAIGPTImageNodeV2` → `SaveImage` |
| 单图参考生成 | `image_reference_api.json` | 单独 `LoadImage` → `model.images.image_1` |
| 多图参考生成 | `image_multi_reference_api.json` | 三个独立 `LoadImage` → `model.images.image_1/2/3` |
| 图生视频 | `seedance20_i2v_api.json` | `LoadImage` → `ByteDance2FirstLastFrameNode.first_frame` → `SaveVideo` |
| 独立配乐 | `music_generate_api.json` | `SoniloTextToMusic` → `SaveAudio` |

图片预设 `gpt-image-2`，字段 `model.size/model.quality/model.background/model.custom_width/model.custom_height`；不再使用旧 `OpenAIGPTImage1`的扁平字段。每张参考应保留自身比例和用途；无需为了拼batch把不同尺寸参考拉伸。多参考图明确标注第1图风格、第2图角色、第3图场景等角色，按本镜相关性绑定，避免把不该出现的人/道具带进来。三参考模板可按当前节点能力增减。

视频预设 **Seedance2.0 Mini**，模型binding允许Mini/Fast；当前二者480p/720p、4–15秒。一般镜头可Mini，复杂接触先测试Fast；不得自动改2.5/Draft。供应商API真实ID可能不同。文字标题和文件名不决定模型，核对节点实际 `inputs.model`。seed仅帮助追溯，不保证相同结果。

## 核对与引用

```bash
python3 "$SKILL_DIR/scripts/workflow.py" doctor --server http://127.0.0.1:8188 --pattern 'OpenAIGPTImage|ByteDance2|Sonilo|LoadImage|SaveImage|SaveVideo|SaveAudio' --out CAPABILITIES_JSON
```

此命令只读，不提交。模板为API图，不是画布布局JSON；UI编辑先导出自己的API图和绑定表，不能把模板节点ID套到别的工作流。用patch改真实widget，保留图像链接：

```bash
python3 "$SKILL_DIR/scripts/workflow.py" patch --graph "$SKILL_DIR/assets/comfyui/seedance20_i2v_api.json" --bindings "$SKILL_DIR/assets/comfyui/seedance20_i2v_bindings.json" --values VALUES_JSON --out SHOT_REQUEST_JSON
```

`VALUES_JSON`示例键为 `model/prompt/image/duration/resolution/ratio/seed/filename_prefix`，值由代理填写实际内容。生图模板则用 `prompt/size/quality/seed/filename_prefix`，单参考加 `image`，多参考加 `image_1/2/3`。`image`值是上传或UI给出的**服务器文件名/子目录**，不是Mac绝对路径。

API上传为 `POST /upload/image`（multipart），服务返回 `name/subfolder/type`后构成真实LoadImage输入；UI上传使用支持的界面操作。保存上传文件名与本地SHA映射，生成引用记录见 [自动执行手册](autonomous-production.md)。仅在prompt写参考文件名不算传入模型。

需要四格统一关键帧板时先生成同一故事的原始大图，再以当前宿主裁切节点逐格保存为单镜图，检查每格身份/比例/动作起点与分格边缘。送视频的是**单张完整首帧**，不能把整张四格板送入。参考图板不是必须步骤，多张独立构图也可。

## 提交、认证与任务

Hosted Partner节点依赖Comfy账号/额度，优先经已登录UI提交；不从浏览器存储提取token，也不把hidden认证写进导出图。只有正式API认证已配置才经API发 `POST /prompt`。缺登录时保存工作流并请求必要登录，不能偷偷换供应商。

提交前运行视频门槛，保存脱敏API图、候选版本与提示词；取得真实 `prompt_id` 和终端Save节点ID即登记。查询使用 `GET /queue`、`/history/{prompt_id}`，产物使用 `/view?filename=...&subfolder=...&type=...`。保存节点当前可能返回 `video`单数字段，收集器同时支持旧 `videos/gifs/images/audio`。

```bash
python3 "$SKILL_DIR/scripts/studio.py" register PROJECT --shot S01 --candidate v1 --server http://127.0.0.1:8188 --task-id ACTUAL_PROMPT_ID --output-node ACTUAL_SAVE_NODE_ID
python3 "$SKILL_DIR/scripts/studio.py" collect PROJECT --server http://127.0.0.1:8188
```

一个镜头一段素材，采用独立付费任务/图，控制并发和用量。未验证的巨型并行图里，某节点失败可能中止其他本地保存，而云端已经收费；没文件不代表没提交。超时先查原任务，不重跑整批。单一工作流可以用于逐镜替换输入，但不能声称整个多服务生产系统只需一张万能图。

4秒请求可能只剪2–3秒，按请求时长估费用。音乐请求须覆盖整片和选段余量，环境底声另行制作/导入。所有原始产物与过程归项目，公开Skill不带用户参考或认证。第三方/自建网关使用其真实节点/文档/导出图，不把Partner模板当所有API通用协议。
