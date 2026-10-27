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
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat)](LICENSE)

# Skill Distill

**Make more of your agent skills.**

Skill Distill helps your agent organize a growing skill library, combine related skills, and check the results on real tasks. It brings shared instructions together while preserving the workflows that make each skill useful.

In every case tested so far, the distilled skills retained their capabilities; in some scenarios, they performed better.

**[Explore the skill](skills/skill-distill/SKILL.md)** · [Get started](#get-started) · [How it works](#how-it-works)

## Why Skill Distill?

As your collection grows, skills can overlap, repeat instructions, or cover different parts of the same task. Figuring out which ones belong together takes work—and simply combining their files can leave important behaviors behind.

Skill Distill helps you:

- **Find candidates.** Group skills by purpose and identify promising ones to distill.
- **Bring workflows together.** Consolidate shared instructions while preserving distinct modes, prerequisites, and branches.
- **Check the result.** Compare the original skills and the distilled candidate on representative tasks.
- **Maintain the result.** Check for source changes, update on request, and restore saved versions.

Depending on the skills, it may recommend a merge, a smaller single skill, shared reference material, or keeping the originals separate. Evaluation reports what was tested, so you can see how much the results cover.

## Get started

Install from your project directory:

```bash
npx skills add izerume/skill-distill --skill skill-distill
```

Ask your agent to take a first look at your library:

```text
$skill-distill Look over my skill library. Group skills by name and description,
then suggest groups worth distilling. Keep this to a quick first pass.
```

Or name the skills you want to combine:

```text
$skill-distill Merge these writing skills while preserving their workflows.
Save the result to distilled/writing-workbench in this project.
Run a quick comparison of the originals and the merged skill, then stop if no issues appear.
```

Continue managing source skills with [npx skills](https://github.com/vercel-labs/skills). Save the distilled skill to a project directory of your choice.

## How it works

1. **Select:** Classify the library, inspect the chosen sources, and decide how to organize them.
2. **Build:** Record source behavior, reconcile overlaps and conflicts, and create a candidate with the necessary workflows and resources.
3. **Evaluate:** Compare the candidate with its sources on individual and combined tasks; report the checks and any observed regressions.
4. **Maintain:** Track source snapshots and saved versions so you can check for changes, update, or restore.

The agent handles semantic decisions and skill generation. Bundled Python helpers manage fingerprints, snapshots, records, and recoverable version operations. Package size and measured runtime cost are reported separately.

## Keep a distilled skill up to date

Check whether its sources have changed:

```text
$skill-distill Check whether writing-workbench's sources have changed. Do not update it yet.
```

When you're ready, update from the installed sources:

```text
$skill-distill Update writing-workbench from the currently installed sources.
Switch after smoke checks pass. Preserve any local edits I have made.
```

You can also restore a saved version:

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
