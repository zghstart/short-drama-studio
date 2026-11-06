---
name: short-drama-studio
description: Develop and produce narrative short dramas from an idea, portrait, script, storyboard, or existing clips. Use for 短剧制作、导演分镜、角色连续性、AI 剧情视频 and finished short films, including screenwriting, generation, sound, captions, editing, and delivery.
---

# Short Drama Studio

把用户当前的输入推进到其要求的交付阶段。负责编剧、导演、分镜、连续性、生成协调和后期；交付成片时完成真实 MP4，不把提示词或任务排队当成成片。

## 确定当前任务

先读本轮相关素材和已有项目，复用已确定的题材、人物、画幅、声音、模型、预算及授权。只询问影响结果且无法从现有信息确定的条件。

| 当前输入或请求 | 从这里开始 |
| --- | --- |
| 想法、人物照、小说片段 | 故事开发；明确虚构人物与故事，不从照片猜现实身份或经历 |
| 只要剧本、分镜、提示词 | 完成对应创作资料；这不自动要求调用生成服务 |
| 已有剧本或分镜 | 保留已认可内容，补齐拍摄与生成所需的真实缺口 |
| 生成样片或完整成片 | 在已有授权和资源范围内推进生成、剪辑与验收 |
| 已有素材或局部问题 | 检查实际文件，从受影响的最小单元修复 |

用户已授权选模型和制作时，不为每张图、每个镜头重复设置确认环节。费用上限、关键创意分叉或无法确定的付费请求结果确实阻塞时，再集中说明。制作授权不等于发布、联系他人或公开原始人像素材的授权。

没有明确画幅时，手机短剧可先采用 9:16；场景数量、演员数量、片长和生成段长按故事与资源决定。不要把某次三段十秒的做法变成所有项目的固定结构。

## 创作与导演

涉及故事、剧本、分镜时读 [故事与导演](references/story-and-direction.md)。

1. 写清主角想得到什么、谁或什么阻碍、主角如何行动、转折如何发生、结果如何落地。短片需要完整的因果链；系列单集也要有本集回报。
2. 根据时长和题材安排信息、动作与反应。先写可演的对白和可见的行动，再拆镜头；不以频繁切镜代替剧情推进。
3. 为每个镜头说明叙事职责、景别与机位、起止状态、表演、对白或画外音、转场和音效。单个生成段可以包含多个可控节拍，复杂动作宜拆开。
4. 写出人物站位、视线、轴线与道具状态。确认机位实际能拍到所描述的面或背，不能同时要求互相矛盾的空间关系。

按需要使用 [简报模板](assets/brief-template.md)、[剧本模板](assets/screenplay-template.md)；不为补齐模板而伪造未完成的上游。

## 人物 场景 道具与参考图

制作重复人物、跨镜头剧情或参考图视频前读 [连续性与提示词](references/continuity-and-prompts.md)。

- 先建立必要的身份、服装、场景、道具和声音参考，使用 [连续性模板](assets/continuity-template.json)。模板中指向的图片必须真实存在，才能作为生成输入。
- 有人物照时，先固定一张适合故事的定妆或场景母帧，再派生不同景别和姿态。脸、发型、眼镜、服装结构、光向及重复道具各有明确依据。
- 区分首帧、尾帧、人物参考、风格参考、声音参考；编号与实际输入顺序一致。首帧里没有人脸时，不把它称作人物身份参考。
- 只给照片并不能确定声音。为角色另选声线；图片生成和配音使用当前环境确实可用、与用户选择匹配的工具或技能。
- 关键中文、文件、界面、署名和精确字幕通常交给后期。镜头中保留合成位置，不让这些文字挤占人物表演。

## 生成与续跑

执行媒体生成前读 [生成执行](references/generation.md)；选择 ZenMux 时再读 [ZenMux 适配](references/zenmux.md)。其他供应商沿用同样的素材、状态和验收约定，按其官方接口实施。

核实当前准确模型 ID、协议、参考能力、时长、音频和分辨率参数。用户要求优惠模型时，记录优惠来源和时间，不把目录中的不同计价项自行解释成折扣。

先做有代表性的镜头测试通常能帮助判断人物和声音是否可用，但用户直接要求完整制作且资源足够时，不强制停在样片阶段。已验收素材可被后续镜头复用。

异步生成时，提交前记录请求摘要，收到任务 ID 后立即保存。轮询和下载均围绕已有 ID 进行。提交超时但不知道服务端是否受理时，保留未知状态并核查，不能自动再提交相同付费请求。成功返回文件后，先检查文件再判断是否需要重做。

ZenMux 辅助工具从环境变量读取凭证，不接收密钥命令行参数：

```bash
python3 "$SKILL_DIR/scripts/zenmux.py" models --output video
python3 "$SKILL_DIR/scripts/zenmux.py" submit \
  --model EXACT_MODEL_ID --prompt ./prompts/shot-01.txt \
  --image ./references/shot-01.png --duration 10 \
  --resolution VERIFIED_VALUE --job ./.drama/jobs/shot-01
python3 "$SKILL_DIR/scripts/zenmux.py" poll --job ./.drama/jobs/shot-01
python3 "$SKILL_DIR/scripts/zenmux.py" download --job ./.drama/jobs/shot-01
```

命令里的时长和分辨率是调用示例，替换为该模型本轮核实的值。只准备方案时使用 `submit --dry-run`，它不读密钥、不请求网络、不提交任务。

## 剪辑 字幕 声音与交付

开始后期时读 [后期与验收](references/post-production.md) 和 [时间线格式](references/manifest.md)。

用实际媒体、实际对白和实际说话时间更新 `film.json`。剧本时码是排演计划，不等于生成结果。生成片段长度与成片取用长度分别记录。

```bash
python3 "$SKILL_DIR/scripts/timeline.py" init ./my-film --title "片名" --duration 30 --shots 3
python3 "$SKILL_DIR/scripts/timeline.py" validate ./my-film/film.json
python3 "$SKILL_DIR/scripts/render.py" ./my-film/film.json --font /path/to/CJK-font.otf
python3 "$SKILL_DIR/scripts/inspect_media.py" ./my-film/output/final.mp4 \
  --expected-duration 30 --expected-fps 30 --require-audio --decode
```

辅助渲染器支持源片音轨、独立配音、背景音乐、字幕与标题；用逐帧透明图层合成，不依赖 FFmpeg 的 `drawtext` 或 `subtitles`。中文需要可读的中文字体。图片、演员、声线和音乐素材按当前工具能力实际制作或使用用户提供的文件。

交付前检查完整解码、实际时长与帧数、画幅、字幕包括最后一句、音轨、对白内容和跨镜头连续性。ASR 核对文字，逐帧检查画面；它们都不能单独证明声线、口型或表演完全一致。

默认交付用户要求的成片及必要说明。保持素材、提示词、任务记录与工程可续作；用户只要成品时，不把中间文件堆给用户。说明尚未验收的关键项目，不把升采样写成模型原生分辨率。

## 随附工具与参考

- `scripts/timeline.py`：初始化项目、检查结构与精确帧时长。
- `scripts/zenmux.py`：当前目录查询、提交、任务续跑、下载、语音转写。
- `scripts/render.py`：按时间线裁切、合成字幕、配音和音乐，输出 MP4 与 SRT。
- `scripts/inspect_media.py`：媒体元信息、完整解码、音频哈希与抽帧。
- [参考项目与设计取舍](references/sources.md)：参考来源、固定版本和本项目的实现边界。
