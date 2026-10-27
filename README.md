<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.png">
  <img src="assets/banner-light.png" alt="Skill Distill" width="1600">
</picture>

**English** | [简体中文](README.zh-CN.md)

[![X: @1zrum](https://img.shields.io/badge/%401zrum-000000?style=flat&logo=x&logoColor=white)](https://x.com/1zrum)
[![CI: GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat&logo=githubactions&logoColor=white)](https://github.com/izerume/skill-distill/actions/workflows/tests.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Agent Skill](https://img.shields.io/badge/Agent_Skill-58B685?style=flat)](skills/skill-distill/SKILL.md)

# Skill Distill

**Turn a growing collection of agent skills into a more coherent toolkit.**

Skill Distill helps your agent find related skills, bring their useful instructions and workflows together, and check the result against real tasks. It also helps you maintain the distilled skill as its sources change.

When several skills cover the same territory, choosing which ones to use—and how to combine them—can become a task of its own. Skill Distill gives your agent a structured way to work through that problem, from a quick library overview to a tested, maintainable skill package.

**In the cases tested so far, distilled skills showed no loss of capability and improved results in some scenarios.**

**[Explore the skill](skills/skill-distill/SKILL.md)** · [How it works](#how-it-works) · [Get started](#get-started)

## What you can do

- **Map your library.** Group skills by purpose and identify promising candidates for consolidation.
- **Distill with the workflows intact.** Bring shared instructions together while keeping distinct modes, prerequisites, and useful branches.
- **Check the result.** Compare the sources and the candidate on representative tasks, and report what was actually tested.
- **Keep it current.** Check for source changes, update when requested, and restore saved versions.

A merge is not always the right answer: the agent can also recommend keeping skills separate, compressing one skill, or factoring out shared material. Results depend on the sources, executor, and evaluation performed; a quick smoke check is evidence about its tested cases, not a guarantee of equivalence.

## Get started

Install in your project directory:

```bash
npx skills add izerume/skill-distill --skill skill-distill
```

Then ask your agent for a quick overview:

```text
$skill-distill Look over my skill library. Group skills by name and description,
then suggest groups worth distilling. Keep this to a quick first pass.
```

Already know what you want to combine? Try:

```text
$skill-distill Merge these writing skills while preserving their workflows.
Save the result to distilled/writing-workbench in this project.
Run a quick comparison of the originals and the merged skill, then stop if no issues appear.
```

Continue managing source skills with [npx skills](https://github.com/vercel-labs/skills). Save distilled skills to the directory you choose in your project.

## How it works

1. **Select:** start with a lightweight classification, then inspect the selected sources and decide whether to merge, factor, compress, or keep them.
2. **Build:** record source behavior and reconcile overlaps, differences, and conflicts into a candidate skill with the necessary branches and resources.
3. **Evaluate:** compare source and candidate behavior on relevant tasks, including individual workflows and combined cases. Report the scope and any observed regressions.
4. **Maintain:** track source snapshots and saved versions, then check, update, or restore as requested.

The agent makes semantic decisions and generates the skill; bundled Python helpers handle fingerprints, snapshots, records, and recoverable version operations. Package size and measured runtime cost are reported separately.

## Maintain a distilled skill

Check for changes without updating:

```text
$skill-distill Check whether writing-workbench's sources have changed. Do not update it yet.
```

Update or restore when you choose:

```text
$skill-distill Update writing-workbench from the currently installed sources.
Switch after smoke checks pass. Preserve any local edits I have made.
```

```text
$skill-distill Restore writing-workbench to r000001.
```

## Further reading

- **Choosing inputs:** [Classification](skills/skill-distill/references/classification.md) · [Target selection](skills/skill-distill/references/target-selection.md)
- **Building and checking:** [Behavior contracts](skills/skill-distill/references/contracts.md) · [Evaluation](skills/skill-distill/references/evaluation.md)
- **Maintenance:** [Updates and restoration](skills/skill-distill/references/versioning.md)

## References and acknowledgements

These works informed the approach to preserving capabilities, composing workflows, and checking candidates on actual tasks:

- [**SkillFusion: Towards Reliable Multi-Skill Composition for LLM Agents**](https://arxiv.org/abs/2610.15481) — Enhao Huang et al., 2026. Constraints with provenance, explicit conflict handling, and instruction deduplication.
- [**SkillComposer: Learning to Evolve Agent Skills for Specification and Generalization**](https://arxiv.org/abs/2606.06079) — Qi Zhang et al., 2026. Creating, merging, and improving skills using task feedback.
- [**One Skill Takes Over: Clashing Agent Skills and a One-File Fix**](https://arxiv.org/abs/2610.25064) — Parsa Razmara, Seyedarmin Azizi, and Ardalan Aryashad, 2026. SkillClash, interference between combined skills, and the importance of correct joint examples.

<details>
<summary><strong>Development and tests</strong></summary>

Python 3.10 or later is required. The internal scripts use the standard library to handle fingerprints, snapshots, and version operations. The agent handles semantic decisions and generation.

Run from the repository root:

```bash
python -X utf8 -B tests/run_tests.py
```

Tests cover target selection, read-only inspection, historical inputs, evidence binding, version switching, and recovery after process exits. They do not call a model. GitHub Actions runs the same suite on Windows and Linux.

</details>
