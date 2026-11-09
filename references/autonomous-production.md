# 自动执行手册

## 接到用户的一句话后

1. 区分“制作成片”“只写方案”“修改Skill”“继续/暂停”。只有前两种制作范围决定是否生成，不因读取Skill就提交模型。
2. 继承已确认的参考、题材、片长、比例、文件目录、服务、预算和禁用型号。未指定时采用入口默认值，不反复问例行创作选择。已有制作授权下，下面各门槛由代理检查并推进，不默认让用户逐个审批。
3. 发现当前工具、可用连接、环境和既有项目，先用已连接的服务。把图片、视频、音乐、语音分别记录到 `generation`。需要的能力是：图像条件生成/编辑、图生视频、足够长度的音乐来源、环境/拟音来源、文件与FFmpeg。ComfyUI可提供其中若干能力，但不是核心依赖。
4. 接入不足时先完成独立创作，再只询问缺少的平台/文档/登录；不猜协议，不要求用户贴API Key。实际登录或宿主写权限受阻时完成其余可做工作并保存明确恢复点。代理无权伪造已提交任务或已通过审片。
5. 在用户输出根目录建 `YYYY-MM-DD_HH-mm-ss_片名_时长s/`。沿用用户时区和既有规范。Skill源码和用户项目分开。

## 阶段、产物与推进条件

| 阶段 | 代理完成的产物 | 推进条件 |
|---|---|---|
| 创作 | 剧本、生活段落、主题、分镜/声音表、空间/道具状态 | 内容多样且相连，总时长准确，动作可实现，`preflight`无矛盾 |
| 视觉基准 | 原创风格锚点、角色、生活圈/室内、必要道具图 | 实际看图接受版本、比例与布局，记录真实文件/哈希 |
| 首帧 | 每镜单张构图、真实参考输入记录 | 参考确实接入；身份、手部占用、支撑与移动净空可行 |
| 试片 | 1–2个风险镜头、实际源片、观察与选段 | 通过所需风格/比例/接触与正常速度运动检查；证据真实 |
| 批量 | 独立镜头请求、任务记录、产物、通过/拒绝候选 | 不扩展失败的试片，不重复未知提交，最多两轮后简化/报告 |
| 剪辑声音 | 有效源区间、连续音乐、空间环境底声、同步拟音/必要对白 | 正常1x，状态可读，声音覆盖，音乐不是每镜重启 |
| 验收 | 最终切口图片、技术报告、实际播放/听检观察 | 文件版本匹配；记录真检查，未做的留pending |
| 归档 | MP4、全部过程、来源、项目与检查记录 | 目录完整可追溯，凭据/临时签名URL不进入公开包 |

公开计划中的 `generation_authorized_for_this_plan=false` 只表示示例自身未授权付费；本次真实用户指令和既有授权优先，不能因此重复要求确认。

先读 [日常叙事](daily-life-storytelling.md)，按新想法重写公开计划，不能只是替换片名。选镜过程同时对照 [美术](art-direction.md)、[细节契约](shot-contracts.md)和 [动作/声音](motion-and-sound.md)。

## 代理维护的引用证据

使用 `studio.py init` 初始化。新项目默认启用 `production_policy`；从旧项目继续制作前补齐该门槛。`reference_assets`、`image_conditioning`、`video_conditioning`用于可核对的资产链：

```json
{
  "reference_assets": [{
    "id": "C01", "role": "角色", "file": "references/C01-v1.png",
    "sha256": "实际文件SHA256",
    "review": {"verdict": "accept", "observations": "实际看到的身份、比例与服装结论", "evidence": ["review/reference-observations.md"]}
  }],
  "production_policy": {"enabled": true, "require_reference_conditioning": true, "require_pilot": true, "pilot_shots": ["S08", "S10"]}
}
```

每镜关联已通过的参考，实际生图后记录：

```json
{
  "required_reference_ids": ["C01", "L04"],
  "image_conditioning": [{
    "reference_id": "C01", "source_sha256": "对应参考图实际SHA256",
    "method": "ComfyUI LoadImage链接 / 服务实际上传方式",
    "input_field": "实际节点或API参考输入字段",
    "evidence_file": "requests/S08-image-v1.json"
  }],
  "image_file": "images/S08-v1.png", "image_sha256": "实际首帧SHA256",
  "image_review": {"verdict": "accept", "observations": "实际看到的双手、杯壶位置、操作净空", "evidence": ["review/S08-image.md"]},
  "video_conditioning": {
    "source_sha256": "实际首帧SHA256", "method": "实际图生视频首帧接入方式",
    "input_field": "实际视频节点/API首帧字段", "evidence_file": "requests/S08-video-v1.json"
  }
}
```

为每个 `required_reference_ids` 建一条实际绑定记录；上例为简写。文件均放项目内，路径、哈希和观察只能在真实产物就绪后填写。`evidence_file`是脱敏的实际请求、工作流或输入截图/记录，保留上传响应的非敏感文件名/资产ID对应关系；不放认证信息。仅有这些字段不能证明图像真的服从了参考，代理仍需检查真实图。

## 视频前置门槛与试片

```bash
python3 "$SKILL_DIR/scripts/studio.py" preflight PROJECT
python3 "$SKILL_DIR/scripts/production.py" PROJECT --stage keyframes
python3 "$SKILL_DIR/scripts/production.py" PROJECT --stage video --shot S08 --request PROJECT/requests/S08-video-v1.json
```

`SKILL_DIR`是实际安装目录，`PROJECT`是当前项目目录；替换示例参数。生成第一张参考图不需要先有已通过首帧；用单独参考资产项目登记图片任务，或 `submit --stage image`，避免把参考素材任务误当正式视频。此处 `keyframes` 检查整集，未完成镜头会阻止整集就绪；先试某镜可单独用 `--stage video --shot` 检查其引用。

`generation.video.allowed_models`用供应商真实模型ID，不用显示名猜API值。默认ComfyUI预设只有 `Seedance 2.0 Mini` / `Seedance 2.0 Fast`。普通HTTP请求可从顶层 `model` 取值；嵌套请求需要 `--model-pointer /实际/字段` 或配置 `model_pointer`。ComfyUI API图检查ByteDance节点的实际 `inputs.model`。读取不到或超出允许清单，停止该次提交，不自动回退。

只有 `pilot_shots`中列出的镜头可在试片未通过前提交。试片成功收集、正常速度检查并接受候选后，登记：

```json
{
  "quality_review": {"pilot": {
    "verdict": "accept", "shot": "S08", "candidate": "v1",
    "source_sha256": "实际试片源视频SHA256",
    "observations": "具体看到的运动、接触、比例、风格结论和检查方法",
    "evidence": ["review/S08-v1/frames.json", "review/pilot.md"]
  }}
}
```

这是记录格式，不是要求照抄的通过结论。候选必须已 `state=success` 且实际审片 `review.verdict=accept`。风险类型不同的第二试片也要实际检查并记录，不因第一镜通过就把其他失败镜头放行。脚本检查指定的代表试片证据，其他镜头的审查由代理执行。

内置直接API `submit --execute --stage video`会在POST前执行这些检查。外部客户端/已登录UI提交也由代理先检查；`register`只是记录已经发生的任务，不会补交、自动审美或撤销费用。

## 成片验收与诚实状态

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose PROJECT
python3 "$SKILL_DIR/scripts/edit.py" cuts PROJECT --handles 3
python3 "$SKILL_DIR/scripts/edit.py" check PROJECT
python3 "$SKILL_DIR/scripts/production.py" PROJECT --stage final
```

实际查看切口图后在 `quality_review.final_cuts`记 `state=passed, method=encoded_cut_frames`；正常速度连续播放后在 `final_visual`记 `state=passed, method=continuous_playback`；实际听取后在 `final_audio`记 `state=passed, method=subjective_listening`。三者均需 `source_sha256`对应当前成片、`observations`和项目内 `evidence`文件。重新合成会清除旧技术/切点报告引用并重置检查状态；旧文件保留，不能把旧审查当新片通过。

`production.py`输出 `ready`表示记录齐备，`can_deliver_test`表示可带待检说明交付测试渲染。出现 `pending_reviews`不准写成“全部验收”；任何工具没有播放/音频理解能力时如实保留pending，也不反复要求用户批准已授权的其他工作。报告里的文字不是工具已观看/已听取的证明。

## 重做、暂停与目录

首帧错误先修图；动作错误修视频；音频错误修声音/混音；修改会影响后镜状态时同步处理依赖。每镜默认最多两个候选；记录缺陷发生秒数、修改变量、真实用量。到限后优先简化接触动作或改变构图，不能无上限撞运气。服务请求结果未知时保留 `submission_unknown`，先查询原任务，恢复不再重交。

```text
YYYY-MM-DD_HH-mm-ss_片名_105s/
  project.json
  planning/       # 易读剧本、主题、分镜、声音表、预演
  references/ images/ clips/ audio/
  requests/ workflows/ logs/
  edit/ review/ final/
```

沿用用户约定；核心检查证据需复制/导入项目内。归档真实来源与可用范围；不要把用户参考视频、商业素材、项目或认证随Skill发布。修改Skill、运行测试与安装不启动新付费生成。
