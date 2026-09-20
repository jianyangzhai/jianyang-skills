# Learning Coach

[中文](README.zh-CN.md) · [Instructions](SKILL.md)

Turn a learning intention into a small, observable result. For learners who want guided practice, a realistic route, or a check of what they actually understand. Four optional modes adapt to the learner's responses; ordinary questions stay ordinary questions.

```bash
DISABLE_TELEMETRY=1 npx skills add https://github.com/jianyangzhai/jianyang-skills --skill learning-coach
```

<!-- attribution:start -->
Built and maintained by [Jianyang Zhai](https://github.com/jianyangzhai) · [@jianyangzhai](https://github.com/jianyangzhai) · [jianyang-skills](https://github.com/jianyangzhai/jianyang-skills)
<!-- attribution:end -->

## What you get

| Mode | Use it when | Observable result |
|---|---|---|
| Time-boxed introduction | You have a limited budget and a concrete task | A representative task you can complete yourself |
| Mistake-focused practice | You want to improve application | An initial attempt, adaptive hints, and a different follow-up problem |
| Personal learning route | You have a goal and deadline | Task-based steps with completion criteria and common mistakes |
| Knowledge-gap check | You think you already understand | Evidence of demonstrated knowledge, untested areas, and a targeted exercise |

The assistant offers the modes once, recommends a fit, and waits for your choice. Explicitly invoking the Skill starts it without repeated confirmation. It uses known context and asks only for missing goals, baseline, or time budget. You can request a direct explanation at any point.

## Install

Use the command above in an Agent Skills-compatible host. The Skill contains Markdown instructions and optional Codex UI metadata; no executable dependencies are bundled. Instruction text is Chinese. Host and model behavior may vary.

Manual alternative: clone this repository and copy the complete `learning-coach` folder into your host's Skill directory. Review existing folders before copying. The CLI command disables installer telemetry; this Skill adds no telemetry or external service.

## Use

- “Use learning-coach. I have 45 minutes to learn enough SQL to group monthly sales. I know SELECT.”
- “Give me a realistic probability problem with a common trap. Let me try first, then use a variation to check understanding.”
- “I have two weeks, 30 minutes a day, to prepare a five-minute technical presentation. Build a realistic route.”
- “I think I understand attention. Ask one diagnostic question at a time and distinguish what I can explain from what I can apply.”

Start with one mode; there is no requirement to complete all four. A session ends with the task completed, observed performance, and a useful next step.

## Evidence and limits

This release is an instruction-only workflow, not an evaluated teaching product. Packaging, metadata, privacy boundaries, and installation can be checked; learning effectiveness has not been measured in a learner study. A correct answer once is not evidence of durable mastery. No hidden model mode, guaranteed learning speed, or superiority claim is made.

For a reproducible behavioral review, follow [the capture checklist](CAPTURE-CHECKLIST.md). It specifies expected behaviors, not fabricated test transcripts. Teaching examples above are suggested prompts, not claimed user outcomes.

The Skill does not automatically write memory, create files, schedule reminders, or publish learner answers. Normal host permissions and fact-checking requirements apply.

## License

MIT for this original implementation and documentation; see [LICENSE](LICENSE). Inspired by four teaching task ideas in 白菜堂's [Xiaohongshu post](https://www.xiaohongshu.com/explore/6aad0845000000002802e3c0), read on 2026-09-19. The implementation rewrites the instructions and removes unsupported claims. Original images and verbatim source prompts are not redistributed; third-party content retains its own rights.
