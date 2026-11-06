# ZenMux 适配

核查日期：2026-11-06。执行时以当前官方文档、目录和服务端返回为准。

- [模型目录](https://zenmux.ai/models)
- [OpenAI 格式列表](https://zenmux.ai/api/v1/models)
- [Vertex 格式列表](https://zenmux.ai/api/vertex-ai/v1beta/models)
- [原生视频 API](https://zenmux.ai/docs/api/zenmux/generate-videos-native.html)
- [Vertex 视频 API](https://zenmux.ai/docs/api/vertexai/generate-videos.html)
- [图片生成](https://zenmux.ai/docs/guide/advanced/image-generation.html)
- [语音转写](https://zenmux.ai/docs/api/openai/create-audio-transcriptions.html)

两个目录的集合可能不同。模型存在不证明支持每种协议、参考模式或音频选项。文档示例与目录ID不同应核对，不从家族名拼别名。

随附视频工具使用原生REST。图片使用当前可用工具、SDK或图片技能；如果已有 `zenmux-image-generation`，读其说明后可复用，不将其列为所有环境的强制依赖。

## 原生视频

```json
{
  "model": "EXACT_MODEL_ID",
  "content": [
    {"type": "text", "text": "本镜动作、表演与声音"},
    {"type": "image_url", "role": "first_frame", "image_url": {"url": "data:image/png;base64,..."}}
  ],
  "duration": 10,
  "ratio": "9:16",
  "resolution": "MODEL_SUPPORTED_VALUE",
  "generate_audio": true
}
```

`POST /api/v1/videos` 返回任务 `id`，`GET /api/v1/videos/{id}` 查询，成功后读 `content.video_url`。常见状态：`queued`、`running`、`succeeded`、`failed`。

首帧、尾帧和其他参考的允许组合依模型而定。工具只实现一张首帧；扩展多参考时保留原生role，不能把顺序当role。

分辨率按模型核实。实际工作中，图片2K配置或视频默认值可能被沿用到只接受另一组值的视频模型。显式传入本轮核实的值，不把某个模型的 `768P` 或某次十秒上限推广到所有模型。

## 凭证与网络

`ZENMUX_API_KEY` 从进程环境读取，不放命令行、模板或Git历史。工具用curl标准输入传鉴权头；`--dry-run` 不读密钥、不联网。

优先使用已有 `HTTPS_PROXY` / `HTTP_PROXY`；macOS未设置时可读现有系统HTTPS代理。只用于当前请求，不改系统代理或全局配置。

任务目录包含参考图数据和可能带签名的URL，保留在项目 `.drama/`，不发布。下载CDN视频不携带API密钥，下载失败继续使用原任务结果。

## 转写

当前接口接受JSON字段 `model`、`input_audio.data`（原始base64，不带Data URI）、`input_audio.format`，可选 `language`。

```bash
python3 "$SKILL_DIR/scripts/zenmux.py" transcribe \
  --model EXACT_ASR_MODEL_ID --audio ./.drama/voice.wav \
  --language zh --out ./.drama/transcript.json
```

ASR模型ID也从当前目录核实。转写不等于已对齐字幕、验证口型或识别声线。
