<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.png">
  <img src="assets/banner-light.png" alt="Skill Distill" width="1600">
</picture>

[English](README.md) | **简体中文**

[![X: @1zrum](https://img.shields.io/badge/%401zrum-000000?style=flat&logo=x&logoColor=white)](https://x.com/1zrum)
[![CI: GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat&logo=githubactions&logoColor=white)](https://github.com/izerume/skill-distill/actions/workflows/tests.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Agent Skill](https://img.shields.io/badge/Agent_Skill-58B685?style=flat)](skills/skill-distill/SKILL.md)

# Skill Distill

**让不断增长的 Agent 技能库，成为更清晰、更好用的工具集。**

Skill Distill 帮助你的 agent 找出相关技能，把有用的指令与工作流整理到一起，并通过实际任务检查结果。源技能发生变化后，它也能帮助你维护蒸馏后的版本。

当多个技能覆盖相近的领域，选择该用哪个、如何组合，本身就会变成一项工作。Skill Distill 为 agent 提供一套有条理的方法：从快速了解技能库，到生成经过检查、便于维护的技能包。

**在目前测试过的所有情况下，蒸馏后的技能都没有出现能力损失，部分场景的表现甚至有所提升。**

**[查看技能](skills/skill-distill/SKILL.md)** · [工作流程](#工作流程) · [开始使用](#开始使用)

## 它能做什么

- **梳理技能库**： 按用途分类，找出值得进一步整理的技能组。
- **保留各自的工作方式**： 整合共同指令，同时保留不同模式、前置条件和必要分支。
- **检查蒸馏结果**： 用代表性任务比较源技能和候选技能，说明实际验证了什么。
- **持续维护**： 检查源技能变化，在你要求时更新，并可恢复已保存的版本。

合并并非唯一选择：agent 也可以建议保留独立技能、压缩单个技能，或提取共享内容。结果取决于源技能、执行环境和实际评测；少量快测只能说明所测试的情况，不能保证所有任务都等价。

## 开始使用

在项目目录中安装：

```bash
npx skills add izerume/skill-distill --skill skill-distill
```

然后让 agent 先快速梳理：

```text
$skill-distill 先看看我的技能库，按名称和描述分类，
挑出值得一起蒸馏的组，暂时不要深入分析。
```

已经知道想合并哪些技能？可以直接说：

```text
$skill-distill 合并这几份写作技能，保留各自的工作方式。
新技能放到当前项目的 distilled/writing-workbench，
快速比较一下原版和融合版，没发现问题就停。
```

源技能继续由 [npx skills](https://github.com/vercel-labs/skills) 管理。蒸馏后的技能放在你指定的项目目录里。

## 工作流程

1. **选择**： 先快速分类，再检查选中的源技能，决定合并、提取共用内容、压缩还是保留。
2. **构建**： 记录源技能的行为，处理重复、差异和冲突，生成包含必要分支与资源的候选技能。
3. **验证**： 用相关任务比较源技能与候选技能，涵盖各自的工作流和组合场景，并说明检查范围与发现的问题。
4. **维护**： 记录来源快照和保存的版本，按要求检查、更新或恢复。

语义判断和技能生成由 agent 完成；随附的 Python 脚本负责指纹、快照、记录和可恢复的版本操作。文件体积与实际运行成本分别衡量。

## 维护蒸馏后的技能

只检查变化，不执行更新：

```text
$skill-distill 检查 writing-workbench 的来源有没有变化，先不要更新。
```

需要时再更新或恢复：

```text
$skill-distill 更新 writing-workbench，使用本机已安装的源，
快测通过后切换。如果有我的本地修改，先保留。
```

```text
$skill-distill 把 writing-workbench 恢复到 r000001。
```

## 进一步阅读

想了解具体方法，可以从这些文档进入：

- **选材**： [分类](skills/skill-distill/references/classification.md) · [目标选择](skills/skill-distill/references/target-selection.md)
- **蒸馏与验证**： [行为契约](skills/skill-distill/references/contracts.md) · [评测方法](skills/skill-distill/references/evaluation.md)
- **后续维护**： [更新与恢复](skills/skill-distill/references/versioning.md)

## 参考文献与致谢

以下研究为能力保留、工作流组合和实际任务验证提供了方法参考：

- [**SkillFusion: Towards Reliable Multi-Skill Composition for LLM Agents**](https://arxiv.org/abs/2610.15481) — Enhao Huang 等，2026。参考其带来源的约束表达、显式冲突处理与指令去重。
- [**SkillComposer: Learning to Evolve Agent Skills for Specification and Generalization**](https://arxiv.org/abs/2606.06079) — Qi Zhang 等，2026。参考其通过任务反馈创建、合并和改进技能的方法。
- [**One Skill Takes Over: Clashing Agent Skills and a One-File Fix**](https://arxiv.org/abs/2610.25064) — Parsa Razmara、Seyedarmin Azizi、Ardalan Aryashad，2026。参考其 SkillClash 任务、技能组合干扰分析，以及对正确联合示例的验证。


<details>
<summary><strong>开发与测试</strong></summary>

需要 Python 3.10 或以上。内部 Python 脚本只使用标准库，辅助计算指纹、保存快照和执行版本操作；语义判断与生成由 agent 完成。

在仓库根目录运行：

```bash
python -X utf8 -B tests/run_tests.py
```

测试覆盖选材、只读检查、历史输入、证据绑定、版本切换和中断恢复，不调用模型。GitHub Actions 配置在 Windows 和 Linux 上执行同一组测试。

</details>
