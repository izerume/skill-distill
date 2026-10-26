# Evidence files and commands

Use Python 3 and resolve `scripts/skill_distill.py` relative to this skill's directory. Quote filesystem paths. `--help` is the command reference. These helpers use the standard library; they do not call an LLM or execute source scripts.

## Snapshot

```text
python scripts/skill_distill.py snapshot --source A=/path/to/skill-a --source B=/path/to/skill-b --out /path/to/new-run
```

The new run contains `sources/A/`, `sources/B/`, and `sources.json` with file hashes. Supply the actual skill package directory, not its containing repository. Existing output directories are refused. Symlinks and directory junctions require the caller to provide a concrete package directory.

## Contract

Write `contract.json` in the run directory. Quotes are verbatim, nonempty substrings identifying the relevant clause. Rule IDs are unique across the run. Include at least one rule mapping for every source; this minimum does not establish extraction completeness.

```json
{
  "schema_version": 1,
  "rules": [
    {
      "id": "A-01",
      "source": {"skill": "A", "file": "SKILL.md", "quote": "Keep prerequisites."},
      "when": "rewriting a technical procedure",
      "behavior": "Retain the conditions required before an operation.",
      "disposition": {
        "action": "merge",
        "target": {"file": "SKILL.md", "quote": "Preserve prerequisites and prohibitions."},
        "reason": "Also covers the equivalent requirement in B."
      }
    }
  ],
  "resources": [
    {
      "source": {"skill": "B", "file": "references/examples.md"},
      "action": "copy",
      "target": "references/B/examples.md"
    }
  ]
}
```

Rule actions: `preserve`, `merge`, `route`, `prioritize`, `drop`. All except `drop` require a target file and quote; routing, prioritization, and dropping require a reason. A drop is reported explicitly and fails the preservation gate, even if structurally well formed. Record duplicate consolidation as `merge` with its surviving target.

Resource actions: `copy`, `adapt`, `omit`. Every source file other than the main `SKILL.md` and product metadata `agents/openai.yaml` needs a decision. `copy` checks byte identity; `adapt` and `omit` require a reason and semantic follow-up. All file paths are relative to the corresponding package and must stay inside it.

```text
python scripts/skill_distill.py validate --run /path/to/run --candidate /path/to/merged-skill --contract /path/to/run/contract.json --out /path/to/run/validation.json
```

The report separates structural validity from semantic preservation. Its frontmatter check is basic; use the host's skill validator for full supported metadata validation. Local inline Markdown links are checked outside code fences. Inspect other resource references in their actual caller syntax.

## Paired results

Cases file:

```json
{"cases": [{"id": "A-01", "stratum": "A-specialist"}]}
```

Each condition has a JSON results file. `checks` contains graded observations, not expectations. Keep raw output and grading evidence with each record or in linked files.

```json
{
  "condition": "candidate-v1",
  "executor": {"model": "same-model-as-baseline", "options": {}},
  "records": [
    {
      "case_id": "A-01",
      "trial": 0,
      "output": "The actual executor response.",
      "checks": [
        {"id": "prerequisite", "passed": true, "critical": true, "evidence": "The response retains the prerequisite."}
      ]
    }
  ]
}
```

Baseline and candidate must contain identical case/trial pairs and the same check IDs and critical flags. Every listed case needs a record. Executor settings must match. If results were produced in batches, include that fact in the run report rather than implying fresh calls per case.

```text
python scripts/skill_distill.py compare --cases /path/to/cases.json --baseline /path/to/baseline.json --candidate /path/to/candidate.json --out /path/to/comparison.json
```

Input validation failures return a nonzero exit status. A valid comparison reporting regressions is still a valid report; read `observed_gate_passed` and the individual cases. Do not convert that field into a statistical noninferiority claim.
