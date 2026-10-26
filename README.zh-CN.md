<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.png">
  <img src="assets/banner-light.png" alt="Skill Distill" width="1600">
</picture>

[English](README.md) | **简体中文** · [![X：@1zrum](assets/x-badge.svg)](https://x.com/1zrum)

# Skill Distill

给 agent 用的技能蒸馏方法：整理你的技能库，把相关 SKILL 合并成更好用的技能，并用实际任务检查原有能力。

信息媒体每天都会推送 SKILL，安装了一个又一个，但是有多少是安装后就遗忘了的，又有多少次你给 agent 发送了十几个 SKILL？

Skill Distill 正试图解决这些问题。它能够在不损失 SKILL 能力、甚至部分场景有所提升的情况下，减少冗余的 SKILL 数量，并压缩体积。

**[阅读 SKILL.md](skills/skill-distill/SKILL.md)**

## 安装

在你的项目目录中运行：

```bash
npx skills add izerume/skill-distill --skill skill-distill
```

安装后，在 agent 中调用 `skill-distill`。例如：

```text
$skill-distill 先看看我的技能库，按名称和描述分类，
挑出值得一起蒸馏的组，暂时不要深入分析。
```

源技能继续由 [npx skills](https://github.com/vercel-labs/skills) 管理。生成的技能放在你指定的项目目录里。

## 它解决什么问题？

### 技能越来越多，不知道该合并哪些

有些技能在重复同一套规则，有些则是一个任务的不同阶段。先把它们按用途分组，才能看清哪些适合共享方法、哪些可以合为一个入口。

Skill Distill 先看名称和描述，给出分类与候选组，再深入你选中的部分。

### 合并了文档，却丢了原来的用法

把内容拼在一起，还不足以处理不同流程之间的关系。素材采集、逐段成文、节拍推进可以共用写作原则，同时保留各自的操作模式。

Skill Distill 会记录源能力、整理共同部分、保留必要分支，再用少量真实任务检查结果。你可以直接指定要合并的技能：

```text
$skill-distill 合并这几份写作技能，保留各自的工作方式。
新技能放到当前项目的 distilled/writing-workbench，
快速比较一下原版和融合版，没发现问题就停。
```

### 源技能更新了，蒸馏版怎么办

Agent 可以检查来源变化，指出哪些蒸馏产物需要更新。你明确说更新后，才基于选定的源重新蒸馏、快测并切换。旧版本会保留，需要时直接恢复。

```text
$skill-distill 检查 writing-workbench 的来源有没有变化，先不要更新。
```

```text
$skill-distill 更新 writing-workbench，使用本机已安装的源，
快测通过后切换。如果有我的本地修改，先保留。
```

```text
$skill-distill 把 writing-workbench 恢复到 r000001。
```

## 进一步阅读

想了解具体方法，可以从这些文档进入：

- **选材：**[分类](skills/skill-distill/references/classification.md) · [目标选择](skills/skill-distill/references/target-selection.md)
- **蒸馏与验证：**[行为契约](skills/skill-distill/references/contracts.md) · [评测方法](skills/skill-distill/references/evaluation.md)
- **后续维护：**[更新与恢复](skills/skill-distill/references/versioning.md)

## 参考文献与致谢

以下研究为能力保留、工作流组合和实际任务验证提供了方法参考：

- [**SkillFusion: Towards Reliable Multi-Skill Composition for LLM Agents**](https://arxiv.org/abs/2610.15481) — Enhao Huang 等，2026。参考其带来源的约束表达、显式冲突处理与指令去重。
- [**SkillComposer: Learning to Evolve Agent Skills for Specification and Generalization**](https://arxiv.org/abs/2606.06079) — Qi Zhang 等，2026。参考其通过任务反馈创建、合并和改进技能的方法。
- [**One Skill Takes Over: Clashing Agent Skills and a One-File Fix**](https://arxiv.org/abs/2610.25064) — Parsa Razmara、Seyedarmin Azizi、Ardalan Aryashad，2026。参考其 SkillClash 任务、技能组合干扰分析，以及对正确联合示例的验证。

技能编写流程也参考了 [gaia-research/skill-fuse](https://github.com/gaia-research/skill-fuse)。README 的组织方式参考了 [mattpocock/skills](https://github.com/mattpocock/skills)。

<details>
<summary><strong>开发与测试</strong></summary>

需要 Python 3.10 或以上。内部 Python 脚本只使用标准库，辅助计算指纹、保存快照和执行版本操作；语义判断与生成由 agent 完成。

在仓库根目录运行：

```bash
python -X utf8 -B tests/run_tests.py
```

测试覆盖选材、只读检查、历史输入、证据绑定、版本切换和中断恢复，不调用模型。GitHub Actions 配置在 Windows 和 Linux 上执行同一组测试。

</details>
