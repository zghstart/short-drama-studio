# 时间线格式

`film.json` 是由剧本、分镜和实际素材派生的剪辑执行单。创意修改回到原有创作文档，再同步受影响镜头；不要让执行单与剧本互相矛盾。

所有时间线区间用整数帧，开始包含、结束不包含。30fps下，十秒是300帧；最后一句结束在 `target_frames`，即可持续到片尾。`in_seconds` 是源文件入点，可含小数。生成时长保留在生成记录，不替代实际媒体参数。

```json
{
  "schema_version": 1,
  "title": "示例短剧",
  "fps": 30,
  "width": 1080,
  "height": 1920,
  "target_frames": 900,
  "fit": "cover",
  "shots": [
    {"id": "S01", "frames": 300, "source": "inputs/shot-01.mp4", "in_seconds": 0, "audio": "source", "purpose": "触发冲突"},
    {"id": "S02", "frames": 300, "source": "inputs/shot-02.mp4", "in_seconds": 0, "audio": "source", "purpose": "人物行动"},
    {"id": "S03", "frames": 300, "source": "inputs/shot-03.mp4", "in_seconds": 0, "audio": "source", "purpose": "结果与回收"}
  ],
  "captions": [
    {"start_frame": 15, "end_frame": 90, "text": "实际对白"},
    {"start_frame": 840, "end_frame": 900, "text": "最后一句"}
  ],
  "titles": [
    {"start_frame": 0, "end_frame": 90, "text": "示例短剧", "position": "top_left"}
  ],
  "music": null,
  "voiceover": null,
  "output": "output/final.mp4"
}
```

- `target_frames` 必须等于全部镜头 `frames` 之和。
- `fit: cover` 保持比例裁切；`contain` 保持完整画面并补边。根据构图选择，不把裁切结果当作原始构图。
- `audio: source` 要求源片有音轨；`silent` 有意静音并生成对应长度的静音轨。
- `captions` 不重叠；同时发生的对白合成一条多行字幕。`titles` 可使用 `top_left`、`lower_left`、`center`；文字可带换行。
- `music` 和 `voiceover` 可为 `{"file":"audio/music.wav","gain":0.15}`。从全片零点开始，过长部分裁切、过短部分补静音，不自动循环。
- 字幕和标题支持可选 `color`（Pillow支持的颜色，如 `#FFE0A0`）。中文通过 `render.py --font` 或顶层 `font` 指定合适字体。
- 路径相对 `film.json` 所在目录解析；执行工具也接受用户提供的绝对路径。公开示例只用相对路径和合成素材。

`timeline.py validate` 只检查计划结构，`--check-files` 再检查素材存在。`render.py` 还会检查源媒体长度、音轨以及输出覆盖风险。
