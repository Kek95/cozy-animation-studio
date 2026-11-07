# 项目格式与执行

脚本使用 Python 3 标准库；视频检查、抽帧和剪辑另需 `ffmpeg`、`ffprobe`。项目放在当前可写工作区，素材工作文件与最终交付目录按宿主约定组织。不要在 Skill 安装目录生成用户项目。

服务配置与路由见 [providers.md](providers.md)；只有选择 ComfyUI 时才需要节点/工作流。

## 初始化与创作

```bash
python3 "$SKILL_DIR/scripts/studio.py" init work/film01 \
  --idea '傍晚整理窗边阅读角，泡一壶茶，和猫一起安顿下来' \
  --title '把傍晚留在窗边' --ratio 16:9
```

初始化后由 Codex 编写 `project.json` 的 `script`、`themes`、`characters`、`scenes` 和 `shots`，并给用户提供易读的剧本/分镜 Markdown。空项目不代表剧本已完成。默认参考 [cozy-episode-project.example.json](../assets/cozy-episode-project.example.json)，按用户本次想法重写。`assets/project-example.json`保留为显式30秒小样示例。

默认正式短片90–120秒，CLI初始化默认105秒；`--duration`可显式覆盖，短样需写明如`--duration 30`。剧本、整集预演、连续性和声音时间由代理维护，现有CLI不自动完成这些创作或审美步骤。见[系列流程](series-production.md)。

每镜最少：

```json
{
  "id": "S01",
  "duration": 4,
  "generation_duration": 5,
  "action": "花园外景，女孩走近番茄架，建立环境",
  "character_ids": ["C01"],
  "scene_id": "L01",
  "reference_files": ["references/style-v1.png", "references/C01-v1.png"],
  "image_file": "images/S01-v1.png",
  "image_prompt": "实际写入完整镜头图提示词",
  "video_prompt": "实际写入动作、运镜和声音提示词",
  "motion_plan": {
    "start_state": "女孩在画面左侧，面向番茄架",
    "beats": ["0–1秒迈步起势", "1–4秒走近番茄架，落脚后停稳", "4–5秒目光转向成熟果实"],
    "secondary_motion": "裙摆跟随步伐摆动，停步后自然回落",
    "camera": "固定中景",
    "cut_cue": "视线落到番茄后切果实细节"
  },
  "candidates": [],
  "selected_candidate": null
}
```

每个项目应维护`story`（愿望、相关行动、变化/互动与结果）、`visual_bible`（已通过视觉基准及版本）、`continuity`（各镜起止状态）和`quality_review`（故事、风格、动作与听检证据）。这些扩展字段供代理实际编写和审查，结构校验不会自动判断其审美质量。

这些路径是项目内的规划示例；文件真正生成并检查后再登记为可用资产。`style_anchor` 保存实际文件路径，`style_review` 保存对照用户参考的结论。单条电影的所有 `duration` 之和应与项目目标一致，`generation_duration` 至少覆盖本镜剪辑长度。

```bash
python3 "$SKILL_DIR/scripts/studio.py" validate work/film01
```

图片也可用单独的参考素材项目登记和收集；`collect` 支持图片/音频/视频结果。`edit.py compose` 只接受视频，不会自动把静态图片冒充动画。

## 一次生成对应一个候选记录

内置直接 API 提交会自动登记候选。通过其他客户端提交后，登记真实服务与任务 ID：

```bash
python3 "$SKILL_DIR/scripts/studio.py" register work/film01 \
  --shot S01 --candidate v1 --task-id ACTUAL_TASK_ID \
  --provider work/video-provider.json --request requests/S01-v1.json --seconds 5
python3 "$SKILL_DIR/scripts/studio.py" collect work/film01 --provider work/video-provider.json
python3 "$SKILL_DIR/scripts/studio.py" status work/film01
```

命令中的 ACTUAL_* 必须来自真实提交；不是可直接执行的示例值。`register` 和 `collect` 不提交或重复生成。`unknown` 表示服务状态未知或任务查询未找到，应先调查；`submission_unknown` 表示提交结果不确定，不能据此重跑。状态中记录的生成秒数是任务用量估计，不是供应商账单。

登记功能如实记录已经提交的任务，即使已经超过建议候选数；它会报告 `limit_exceeded`，不会删掉已发生的生成。**额度与重试上限由代理在提交之前检查**。内置 `submit --execute` 会在提交前检查候选上限。若多实例同时修改同一项目，需要外部串行化；当前脚本不提供跨进程任务调度或多写者锁。

## 审片与局部重做

```bash
python3 "$SKILL_DIR/scripts/edit.py" inspect work/film01/clips/S01/v1-00.mp4 --decode
python3 "$SKILL_DIR/scripts/edit.py" frames work/film01/clips/S01/v1-00.mp4 \
  --out work/film01/review/S01-v1 --count 12
```

实际看图/播放，填写可核实的理由；不要把“抽帧成功”写成“画风检查通过”。动作镜头需正常速度检查完整过程，密集取样用于定位身体运动、液体、手部和物体接触问题，不能替代动态观感验收。音频需播放或使用音频理解能力检查；仅有音轨不能证明有背景音乐、对白正确或没有杂音。无法连续观看/听取时保留对应待检状态，见 [动作与声音](motion-and-sound.md)。

```bash
python3 "$SKILL_DIR/scripts/studio.py" review work/film01 \
  --shot S01 --candidate v1 --verdict accept --trim-in 0.5 \
  --note '已查看动作过程，人物与参考一致；选择从0.5秒起的4秒。'
```

拒绝时用 `--verdict reject` 并记录具体问题。用同一套已通过参考图、调整一个主要变量，生成 v2。只有动作坏了就重做视频；构图或身份从首帧就错了，先修镜头图。不要反复添加相互矛盾的形容词。

## 剪辑和配音

新项目默认需要背景音乐。取得音乐文件后登记项目相对路径和来源，例如：

```json
{
  "audio": {
    "music_required": true,
    "music": "audio/music-v1.wav",
    "music_brief": "30秒原创无歌词器乐，开头进入、生活动作中推进、结尾自然收束",
    "music_source": {"kind": "user_supplied", "note": "填写真实来源与使用依据"},
    "voiceover": null,
    "native_audio": true
  }
}
```

路径只在真实文件就绪后填写。`music_required=true` 且没有音乐时，最终合成会拒绝继续；规划阶段允许路径为 null。用户明确选择无配乐时设为 false，并清空音乐路径。旧项目未声明该字段时保持原兼容行为，代理应按用户本次要求补齐。

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose work/film01 \
  --out outputs/film01.mp4 --width 1280 --height 720 --fps 24
```

脚本按 storyboard 顺序使用已通过的候选，从 `trim_in` 裁取 `duration`；拒绝不足的源视频，不通过静帧延长掩盖缺素材。默认中心裁切到目标比例，必要时使用 `--fit pad`，或按主体位置另行编写剪辑。选择与实际素材匹配的输出规格；放大像素不是提升真实清晰度。

配音由用户选择的 TTS API、工具或可选节点流程生成，音乐由用户素材或已授权生成服务取得，记录来源。脚本只负责混入音轨，不内置 TTS 或音乐模型。自动读取 `audio.music` 和 `audio.voiceover` 的项目相对路径，CLI `--music` / `--voice` 优先且相对当前工作目录。`audio.native_audio=false` 或 `--mute-native` 静音片段原声。需要配音时调用当前环境相应技能/工具，先测真实时长：

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose work/film01 \
  --out outputs/film01-vo.mp4 --voice work/film01/audio/narration.wav \
  --music work/film01/audio/music.wav --music-db -16 --native-db -4 --duck-music
```

旁白从 0 秒开始；需要逐句错位时先用 FFmpeg 生成已经对齐的旁白轨，再混入。音乐短于成片时默认报错，仅在确实适合循环时使用 `--loop-music`。这里给出的音量是命令示例，要按实测响度和实际听感调整。

剪辑输出附带技术报告：时长、分辨率、音轨、完整解码以及实际混入的音频路径、增益和循环标记。报告中的听检默认仍是 pending，不会因有音轨就自动通过。最后分别记录 `quality_review.motion` 与 `quality_review.final_audio` 的检查证据，检查最终画面的接缝、声音和叙事节奏。以宿主可显示的视频方式呈现本地 MP4。

## 批量与继续项目

同系列多个主题各用一个项目 JSON。共用角色和场景参考，可通过绝对路径或复制文件引用并记录来源。先完成一条代表性短片，确认风格方向后复用到系列；如用户已经认可当前视觉设定，直接继续，不重复请求确认。

再次打开任务时，读项目文件和候选状态，按每个候选的 provider 分别收集现有任务，继续未完成阶段。Skill 由 Codex 执行；持续无人值守运行需另配常驻调度程序，本包不声称提供后台服务。

## 镜头契约预检

按 [shot-contracts.md](shot-contracts.md) 填写 `motion_plan.speed_mode/active_seconds`、`interaction` 和 `continuity`。完成剧本后、视频请求提交前运行：

```bash
python3 "$SKILL_DIR/scripts/studio.py" preflight work/film01
```

旧项目和旧的30秒/农村题材示例仍可用原 `validate` 读取，不自动改写历史。要进入新一轮视频制作，先补齐镜头契约再预检。预检不发出API请求、不修改项目，也不验证画面或提示词是否被模型服从。代理必须将本镜相关契约落实到最终实际发送的 `video_prompt`，保留请求文本，并另行审看生成结果。
