# 参考项目与设计取舍

研究日期：2026-11-06至2026-11-07。以下链接固定到当次观察版本。本项目的流程说明、Python工具和合成测试由本项目实现。

| 来源 | 观察到的组织方式 | 本项目采用的思路 |
| --- | --- | --- |
| [Dramake](https://github.com/xixihhhh/ai-short-drama-skill/blob/38345d39b27eb877978422bff28b5057e783164f/skills/dramake/SKILL.md) | 故事、资产、分段生成、声音、质检形成生产流程；细节分到参考资料 | 将制作当作有状态的整体，先定位当前输入阶段，保持上游与成片的对应关系 |
| [drama-skills 创作路由](https://github.com/zenstory-ai/drama-skills/blob/ee0ac8ba8775b07a7470c67f5d544469d8c0206b/skills/short-drama/SKILL.md) 与 [分镜技能](https://github.com/zenstory-ai/drama-skills/blob/ee0ac8ba8775b07a7470c67f5d544469d8c0206b/skills/short-drama-storyboard/SKILL.md) | 从用户已有创作阶段进入，创作文档与生产执行分工，关键帧有明确依据 | 支持局部入口，区分计划中的素材与实际可用参考，使用可追溯镜头 ID |
| [short-drama-agent](https://github.com/MrMO0802/short-drama-agent/blob/ac4a4a92d282d3d10fd30d4eb7e0d95359a193f2/SKILL.md) | 资产提取、导演分镜、连续性和提示词相连 | 记录空间、人物和道具起止状态，明确每个参考的职责 |
| [Remotion captions](https://github.com/remotion-dev/skills/blob/a2824c67f8b4585c294a8101db9f9f0ad3c643f8/skills/remotion-captions/SKILL.md) 与 [render](https://github.com/remotion-dev/skills/blob/a2824c67f8b4585c294a8101db9f9f0ad3c643f8/skills/remotion-render/SKILL.md) | 精简入口按需加载渲染与字幕资料，字幕使用结构化时序 | 保持入口简短，创作说明与执行工具分离，以可验证时间线管理字幕 |
| [OpenAI Skills](https://developers.openai.com/api/docs/guides/tools-skills) 与 [技能评估](https://developers.openai.com/blog/eval-skills) | SKILL.md 加可选参考、脚本和资产；验证真实任务表现 | 采用标准目录，并用离线媒体、状态恢复和末帧字幕做行为测试 |

## 从实际制作提炼的工程处理

- 将剪辑镜头、生成请求和最终取用时长分开，支持不同模型与片长。
- 模型参数和折扣在执行时核实；将供应商细节留在可替换的适配层。
- 提交前落盘，保留未知提交状态；收到任务 ID 后续跑同一任务。
- API凭证只经进程环境与请求头传递，媒体下载不转发凭证。
- 不依赖FFmpeg文字滤镜，用逐帧透明图层确保最后一句字幕不提前消失。
- 技术验收、对白转写与视觉/听觉判断分别记录，不以自动检查替代创作判断。

本仓库采用MIT许可。上表项目的内容与许可由各自仓库维护；原始项目文件和参考媒体不包含在本仓库中。
