# 项目格式与执行命令

先读 [自动执行手册](autonomous-production.md)。脚本使用Python3.10+标准库，媒体处理需要FFmpeg/ffprobe。`SKILL_DIR`替换为实际安装目录、`PROJECT`替换为项目目录；不在Skill源码内生成用户素材。

## 初始化与计划

```bash
python3 "$SKILL_DIR/scripts/studio.py" init PROJECT --idea '雨后逛店、回家画画，窗边喝饮料休息' --title '把日子放轻一点'
```

默认105秒、16:9、`daily_montage`；显式短片加 `--duration 30`，完整单一过程可加 `--story-mode single_process`。初始化创建空计划和目录，不会自动写剧本或发请求。Codex维护 `script/themes/story/characters/scenes/shots`、易读剧本/分镜与声音表。

从 [105秒计划](../assets/cozy-episode-project.example.json)或 [30秒计划](../assets/daily-montage-30s-project.example.json)学习格式；重写内容，不照抄完成状态。`duration`是编辑用时，`generation_duration`是模型请求用时；总编辑时长准确，生成秒数另行预算。每镜契约字段见 [shot-contracts.md](shot-contracts.md)。

```bash
python3 "$SKILL_DIR/scripts/studio.py" validate PROJECT
python3 "$SKILL_DIR/scripts/studio.py" preflight PROJECT
python3 "$SKILL_DIR/scripts/production.py" PROJECT --stage plan
```

`validate`检查基础结构/时长；`preflight`检查提示词、正常速度、动作顺序、布局版本、道具状态变化/省略。它们不检查像素。新项目启用 `production_policy`，引用/试片记录格式和阶段命令见自动执行手册；旧项目兼容读取，继续新制作时应补齐门槛。

## 提交、登记与恢复

直接JSON HTTP接口按 [providers.md](providers.md)配置。请求格式必须来自当前服务文档。预演不POST，正式提交加 `--execute`：

```bash
python3 "$SKILL_DIR/scripts/studio.py" submit PROJECT --provider PROVIDER_JSON --shot S08 --candidate v1 --request REQUEST_JSON --stage video
python3 "$SKILL_DIR/scripts/studio.py" submit PROJECT --provider PROVIDER_JSON --shot S08 --candidate v1 --request REQUEST_JSON --stage video --execute
```

嵌套模型字段加 `--model-pointer /实际/字段`，或配置 `model_pointer`。正式视频提交在POST前核对计划、参考/首帧哈希、试片与模型允许清单。图片/音乐/配音任务可在独立资产项目登记，使用对应 `--stage image|music|speech`，不误用正式视频门槛。

其他工具/SDK/UI已经提交后，只登记真实任务：

```bash
python3 "$SKILL_DIR/scripts/studio.py" register PROJECT --provider PROVIDER_JSON --shot S01 --candidate v1 --task-id ACTUAL_TASK_ID --request REQUEST_JSON --seconds 4
python3 "$SKILL_DIR/scripts/studio.py" collect PROJECT --provider PROVIDER_JSON
python3 "$SKILL_DIR/scripts/studio.py" status PROJECT
```

ComfyUI另需真实 `--output-node SAVE_NODE_ID`。ACTUAL值来自真实响应，不能照抄占位符。`register/collect`不补交任务。`unknown/submission_unknown`先查原任务，不能当失败重新POST；内置提交先记待提交候选，结果不确定需核实后用 `register --recover`绑定真实任务ID。

候选默认上限2，登记已发生任务不会抹掉超额事实；并发多写者需要外部串行化，本工具不提供跨进程锁。项目有多个provider时按候选服务分别收集，恢复先读原状态。

## 审片与选段

```bash
python3 "$SKILL_DIR/scripts/edit.py" inspect PROJECT/clips/S08/v1-00.mp4 --decode
python3 "$SKILL_DIR/scripts/edit.py" frames PROJECT/clips/S08/v1-00.mp4 --out PROJECT/review/S08-v1 --count 18
```

实际看图和正常速度播放，观察风格/身份/比例/接触/运动；抽帧只是定位证据。视频有音轨不能证明配乐存在或听感合格。无法连续播放/听取的检查保留pending。

```bash
python3 "$SKILL_DIR/scripts/studio.py" review PROJECT --shot S08 --candidate v1 --verdict accept --trim-in 0.875 --note '填写实际观察、所选区间与理由'
```

只接受真实收集/导入的候选。拒绝记具体秒数和缺陷，新版候选保留旧记录；首帧错先修图，运动错修视频，按依赖更新后镜状态。

## 音乐、环境与混音

取得真实素材后设置项目内路径和来源，尚未生成时为null：

```json
{"audio": {
  "music_required": true, "music": "audio/music-v1.wav", "music_offset": 0,
  "music_source": {"kind": "generated", "note": "实际服务、模型、提示词与任务记录位置"},
  "ambience_required": true, "ambience": "audio/ambience-bed.wav", "ambience_offset": 0,
  "voiceover": null, "native_audio": true
}}
```

环境底声可由服务生成、用户素材或已授权素材在外部编辑成空间衔接的一条轨道；不能让市集喧闹贯穿安静室内。需要对白时先生成与测量，制作一条已经逐句对齐的整片语音轨。脚本不是语音/音乐模型。

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose PROJECT
```

默认输出 `PROJECT/final/film.mp4`，1280×720、24fps、正常1x，自动读取项目音频。需其他规格显式给 `--width/--height/--fps` 并更新项目 `delivery`。默认中心裁切，可 `--fit pad`；需要选取画面局部时每镜 `edit_crop=[x,y,width,height]`，必须在源分辨率内且不能据此把重复镜头当新覆盖。镜头时长须落在输出整帧，trim入点按输出帧网格对齐并记录请求值/实际值。源片不够会报错，不冻结延长。

CLI音频路径相对当前目录且优先于项目路径；例：

```bash
python3 "$SKILL_DIR/scripts/edit.py" compose PROJECT --out PROJECT/final/film-v2.mp4 --voice PROJECT/audio/dialogue.wav --music PROJECT/audio/music-v1.wav --ambience PROJECT/audio/bed.wav --music-db -2 --duck-music
```

默认实测源响度后分层增益（原生约−29、音乐−23、语音−20、环境−35 LUFS，另有峰值保护），再两遍整片处理至约−18 LUFS、−2dBTP、48kHz立体声。`--music-db`等是归一化基础上的额外相对调整，默认0；不是旧版的固定绝对衰减。`--no-normalize-audio`可显式关闭自动响度处理。技术目标是起点，最终以听感调整。`--duck-music`需语音和音乐，保留环境轨。

可用 `--music-offset/--ambience-offset`选素材起点。音乐或环境不足默认拒绝，只有明确适合循环才加 `--loop-music/--loop-ambience`并记来源；不默认循环填满。可用服务无法一次生全长时，代理生成同主题段落并编辑衔接。用户明确无配乐/无环境可关闭相应required字段，不能为了绕过缺素材而偷偷关闭。静音片需显式声明。

合成生成媒体报告、素材SHA/实际区间/裁切/增益/循环记录、`edit/timeline.json`，并登记 `final_file`。输出不覆盖旧文件，重新合成重置最终审核状态。

## 真正的切口和技术检测

```bash
python3 "$SKILL_DIR/scripts/edit.py" cuts PROJECT --handles 3
python3 "$SKILL_DIR/scripts/edit.py" check PROJECT
python3 "$SKILL_DIR/scripts/production.py" PROJECT --stage final
```

`cuts`根据合成报告对**已编码成片**逐切口取前后各3帧，输出每切一行JPEG、每页5行联系图及帧索引映射；左侧为前镜真实出点，右侧为后镜真实入点。报告SHA/时间线变更会拒绝旧证据。提取成功不会自动标为已看。

`check`执行严格全片解码、时长/尺寸/fps、音频48kHz立体声与覆盖、响度/峰值、黑场、解码帧数和完全重复帧检测。重复帧只是需要检查的警告，不自动断言动作卡顿；预期黑场需 `delivery.allow_black_intervals=true`且实际复核。输出技术报告并绑定成片SHA，不声称完成主观播放/听检。

最终三项实际审查记录格式见自动执行手册。交付MP4时同时给出实际完成和待检事项，沿用时间目录归档。共享系列素材先复制/导入项目并记录来源，保持当前项目的哈希链可核对。以宿主支持的本地媒体预览方式展示成片。
