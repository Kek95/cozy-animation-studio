# 项目格式与执行

脚本使用 Python 3 标准库；视频检查、抽帧和剪辑另需 `ffmpeg`、`ffprobe`。项目放在当前可写工作区，素材工作文件与最终交付目录按宿主约定组织。不要在 Skill 安装目录生成用户项目。

服务配置与路由见 [providers.md](providers.md)；只有选择 ComfyUI 时才需要节点/工作流。

## 初始化与创作

```bash
python3 "$SKILL_DIR/scripts/studio.py" init work/film01 \
  --idea '夏天傍晚，女孩在花园里摘番茄，为奶奶做一顿晚饭' \
  --title '傍晚的一篮番茄' --duration 30 --ratio 16:9
```

初始化后由 Codex 编写 `project.json` 的 `script`、`themes`、`characters`、`scenes` 和 `shots`，并给用户提供易读的剧本/分镜 Markdown。空项目不代表剧本已完成。参考 `assets/project-example.json`，但必须按用户本次想法重写。

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
  "candidates": [],
  "selected_candidate": null
}
```

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

实际看图/播放，填写可核实的理由；不要把“抽帧成功”写成“画风检查通过”。身体运动、液体、手部和物体接触需更密集取样。音频需播放或使用音频理解能力检查；仅有音轨不能证明对白正确或没有杂音。

```bash
python3 "$SKILL_DIR/scripts/studio.py" review work/film01 \
  --shot S01 --candidate v1 --verdict accept --trim-in 0.5 \
  --note '已查看动作过程，人物与参考一致；选择从0.5秒起的4秒。'
```

拒绝时用 `--verdict reject` 并记录具体问题。用同一套已通过参考图、调整一个主要变量，生成 v2。只有动作坏了就重做视频；构图或身份从首帧就错了，先修镜头图。不要反复添加相互矛盾的形容词。

## 剪辑和配音

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose work/film01 \
  --out outputs/film01.mp4 --width 1280 --height 720 --fps 24
```

脚本按 storyboard 顺序使用已通过的候选，从 `trim_in` 裁取 `duration`；拒绝不足的源视频，不通过静帧延长掩盖缺素材。默认中心裁切到目标比例，必要时使用 `--fit pad`，或按主体位置另行编写剪辑。选择与实际素材匹配的输出规格；放大像素不是提升真实清晰度。

配音由用户选择的 TTS API、工具或可选节点流程生成，音乐由用户素材或已授权生成服务取得，记录来源。脚本只负责混入音轨，不内置 TTS 或音乐模型。需要配音时调用当前环境相应技能/工具，先测真实时长：

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose work/film01 \
  --out outputs/film01-vo.mp4 --voice work/film01/audio/narration.wav \
  --music work/film01/audio/music.wav --music-db -16 --native-db -4 --duck-music
```

旁白从 0 秒开始；需要逐句错位时先用 FFmpeg 生成已经对齐的旁白轨，再混入。音乐短于成片时默认报错，仅在确实适合循环时使用 `--loop-music`。这里给出的音量是命令示例，要按实测响度和实际听感调整。

剪辑输出附带技术报告：时长、分辨率、音轨、完整解码。最后仍需检查最终画面的接缝、声音和叙事节奏。以宿主可显示的视频方式呈现本地 MP4。

## 批量与继续项目

同系列多个主题各用一个项目 JSON。共用角色和场景参考，可通过绝对路径或复制文件引用并记录来源。先完成一条代表性短片，确认风格方向后复用到系列；如用户已经认可当前视觉设定，直接继续，不重复请求确认。

再次打开任务时，读项目文件和候选状态，按每个候选的 provider 分别收集现有任务，继续未完成阶段。Skill 由 Codex 执行；持续无人值守运行需另配常驻调度程序，本包不声称提供后台服务。
