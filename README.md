**English** | [简体中文](README.zh-CN.md)

<img src="assets/icon.svg" width="64" height="64" alt="">

# Skill Distill

Help your agent organize its skill library, combine related skills, and check the result on real tasks.

**[Read SKILL.md](skills/skill-distill/SKILL.md)**

## Installation

Run this in your project directory:

```bash
npx skills add izerume/skill-distill --skill skill-distill
```

Then invoke `skill-distill` in your agent. For example:

```text
$skill-distill Look over my skill library. Group skills by name and description,
then suggest groups worth distilling. Keep this to a quick first pass.
```

Continue managing source skills with `npx skills`. Save distilled skills to the directory you choose in your project.

## What does it help with?

### Too many skills, and no clear place to start

Some skills repeat the same rules. Others handle different stages of a task. Grouping them by purpose reveals which can share methods or a common entry point.

Skill Distill starts with names and descriptions, suggests groups, then inspects the sources for the groups you select.

### Merged instructions lose the original workflow

Related workflows can share principles while keeping their own interaction patterns. Collecting fragments, shaping an article, and choosing writing beats are a useful example.

Skill Distill records source capabilities, consolidates shared material, preserves the necessary branches, and checks the result on a small set of real tasks. You can name the skills to merge:

```text
$skill-distill Merge these writing skills while preserving their workflows.
Save the result to distilled/writing-workbench in this project.
Run a quick comparison of the originals and the merged skill, then stop if no issues appear.
```

### Keeping distilled skills up to date

Your agent can check for source changes and identify affected outputs. An explicit update request starts a rebuild from the selected sources, followed by smoke checks and a switch to the new version. Saved packages remain available for restoration.

```text
$skill-distill Check whether writing-workbench's sources have changed. Do not update it yet.
```

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

<details>
<summary><strong>Development and tests</strong></summary>

Python 3.10 or later is required. The internal scripts use the standard library to handle fingerprints, snapshots, and version operations. The agent handles semantic decisions and generation.

Run from the repository root:

```bash
python -X utf8 -B tests/run_tests.py
```

Tests cover target selection, read-only inspection, historical inputs, evidence binding, version switching, and recovery after process exits. They do not call a model. GitHub Actions runs the same suite on Windows and Linux.

</details>
