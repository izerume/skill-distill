# Select targets by behavior and benefit

Choose among keeping independent skills, compressing one skill, sharing reference material, and fusing genuinely overlapping behavior. The output of this stage is an actionable build proposal, not an already-validated replacement.

## Classify, scope, assess, select

Use `scripts/skill_distill.py` relative to this package. Paths below are examples; use the user's actual roots and keep reports outside source package directories.

For a library-wide request, first follow [classification](classification.md) using names and descriptions. Deliver a lightweight category map before detailed analysis. Continue below only for selected task families, or directly for sources the user explicitly names.

```text
python -X utf8 -B scripts/skill_distill.py select --root /path/to/skill-library --classification classification.json --category motion --out inventory.json
```

Repeat `--root` for multiple libraries or explicitly named packages. The scanner reads packages without executing their instructions or scripts, distinguishes same-name packages by their IDs and paths, inventories metadata/resources, and reports exact duplicates. It stops inside a found package, so a bundled example SKILL.md is not another installed skill. Skipped or unreadable paths appear in diagnostics.

The first detailed run provides resource inventory and a bounded lexical shortlist for the chosen scope. Classification retains complete category groups, including complementary roles and platform branches; consider those groups alongside pairs. `plan.unassessed` is a review queue, not a keep decision. Review selected entrypoints for internal repetition and conditional-disclosure opportunities, using single-member assessments where useful. Full-library single-skill coverage is needed only when that deeper audit is requested. Name, description or paragraph similarity does not establish duplicated behavior; repeated example labels and code scaffolding are not redundancy evidence.

The calling agent completes the semantic stage automatically:

1. Read candidate entrypoints and relevant linked resources as source material. Identify their activation conditions, behavior, distinct workflow branches, tool/environment requirements and invocation policies. Follow through the referenced code when it changes compatibility.
2. Write `assessments.json` with the facts below and verbatim evidence from every member. Different steps in one workflow are not duplicates merely because they are often used together. Shared reference material needs identifiable common substance, not just a generic writing preference.
3. Re-run the selector with those assessments and any actual usage records. Read every selected action and excluded alternative. Continue source inspection when a material group remains unassessed; do not turn unknowns into claims of equivalence.

```text
python -X utf8 -B scripts/skill_distill.py select --root /path/to/skill-library --classification classification.json --category motion --assessments assessments.json --out selection.json
```

The selector validates quoted evidence against actual package files and resolves conflicts between proposed changes. Compression and fusion reserve their whole source packages. Reference extraction reserves its quoted source regions: one package can contribute distinct material to more than one extraction, while the same region cannot be extracted twice. Assess a multi-skill common reference directly when it can replace fragmented pairwise extractions; graph connectivity alone does not establish common material. Preserve why alternatives were rejected or deferred. Do not ask the user to hand-author this JSON when the source can answer the questions; producing it is part of using this skill.

## Semantic assessment format

```json
{
  "groups": [
    {
      "members": ["/absolute/path/to/alpha", "/absolute/path/to/beta"],
      "task_overlap": "same",
      "behavior_overlap": "high",
      "workflow": "compatible",
      "shared_reference": false,
      "internal_redundancy": false,
      "reason": "Both enforce the caller-selected format during the same rewriting task; their distinct modes can remain explicit.",
      "evidence": [
        {
          "skill": "/absolute/path/to/alpha",
          "file": "SKILL.md",
          "quote": "Preserve the requested output format.",
          "kind": "shared_behavior"
        },
        {
          "skill": "/absolute/path/to/beta",
          "file": "SKILL.md",
          "quote": "Keep the output format requested by the caller.",
          "kind": "shared_behavior"
        }
      ]
    }
  ]
}
```

Replace the example paths and quotes with actual evidence. Members and evidence skill references accept inventory IDs or absolute package paths, not ambiguous display names.

- `task_overlap`: `same`, `partial`, `different`.
- `behavior_overlap`: `high`, `partial`, `none`.
- `workflow`: `compatible`, `branchable`, `complementary`, `conflicting`, `unrelated`.
- `shared_reference`: whether substantial reference content can be shared while preserving entrypoints.
- `internal_redundancy`: whether a single skill repeats behavior under the same conditions.
- Evidence `kind`: `shared_behavior`, `shared_reference`, `repetition`, `boundary`, `unique_behavior`.
- Optional evidence `occurrence`: zero-based occurrence of the quoted text. Distinct repetition requires distinct source spans; listing one occurrence twice is not evidence of two copies. Equivalent behavior may use different wording. Quotes and character offsets use universal-newline text; hashes preserve original file bytes.

Use `boundary` and `unique_behavior` evidence to record what an intervention must preserve, not only favorable overlap. Evidence substring checks establish provenance, not semantic completeness; the semantic judgment remains attributable to its author.

## Compare all four actions

- **keep:** retain independent skills when behavior is complementary, scopes or invocation policies differ, expected benefit is nonpositive, or material evidence is missing. This is successful selection, not a failure to distill.
- **compress:** consolidate source-backed repeated behavior, or move genuinely conditional substantial branch material behind precise reference pointers. Preserve the full branch and all always-required core instructions. File length alone is not a compression reason.
- **factor:** share substantive reference material while preserving separate entrypoints, workflows and activation policy. A shared topic alone does not justify extracting a new reference.
- **merge:** strong shared behavior with compatible/branchable workflows can justify a combined candidate. Partial overlap also qualifies when an evidenced shared step/context and an explicit composition plan preserve every source route and ordering constraint. Fully different tasks, conflicting requirements and mismatched/unknown invocation policies still block fusion. Co-use alone is not shared behavior.

### Conditional disclosure within one skill

An optional `disclosure_plan` supports compression without falsely claiming internal duplication:

```json
{
  "keep_core": "Keep common constraints and mode dispatch in the entrypoint.",
  "branches": [
    {
      "file": "SKILL.md",
      "quote": "A real source paragraph or block for this conditional branch.",
      "occurrence": 0,
      "when": "The actual task condition requiring this material",
      "preserve": "Move the whole branch with its prerequisites, examples and resources intact."
    }
  ],
  "checks": ["The relevant request reaches the complete branch", "Unrelated requests retain the shared core without loading this detail"]
}
```

Each branch must refer to an already verified `unique_behavior`, `boundary` or `repetition` evidence span in that single-member group. Keep `internal_redundancy=false` if the opportunity is disclosure rather than duplication. A bare heading or an unconditional link to the whole original entrypoint does not establish useful disclosure.

### Consolidating a partial-overlap workflow

An optional `composition_plan` makes partial workflow fusion reviewable:

```json
{
  "strategy": "branches",
  "shared_context": "The concrete signal, state or decision loop being reused",
  "routes": [
    {"skill": "/absolute/path/to/alpha", "when": "Alpha's actual activation condition", "preserve": "Alpha's modes, prerequisites, outputs and side effects"},
    {"skill": "/absolute/path/to/beta", "when": "Beta's actual activation condition", "preserve": "Beta's independent capability and boundary"}
  ],
  "ordering": "State the dependency ordering or how independent branches stay independent.",
  "checks": ["Alpha-only behavior survives", "Beta-only behavior survives", "Shared execution obeys both dependencies", "Negative activation remains correct"]
}
```

`strategy` is `branches` or `pipeline`. Routes must cover every member once. Partial-overlap fusion requires a `shared_behavior` quote and `unique_behavior` or `boundary` evidence from every member. `workflow=conflicting`/`unrelated`, `behavior_overlap=none`, or different/unknown invocation declarations remain ineligible even with a plan. Calling an already-shared skill is reuse, not another copy of its implementation.

A metadata requirement for explicit-only invocation remains significant even when the two descriptions sound alike. Unknown or conflicting policy declarations need source/host clarification before fusion; shared references can preserve separate activation boundaries. Favor the lower-complexity adequate option when alternatives have comparable support. Repeating a requirement at distinct workflow phases can be necessary: retain an initial gate and a final verification when they have different jobs.

Selection does not write, delete, install or activate skills. Apply an intervention only when the user's task authorizes that work, and evaluate actual task behavior before treating a candidate as a replacement.

## Optional usage and economics

Pass aggregated observations and forecasts with `--usage usage.json`. Do not read secrets or full conversations just to obtain counts. Without supplied records, frequency and co-use stay unknown.

```json
{
  "events": [
    {"skills": ["/absolute/path/to/alpha", "/absolute/path/to/beta"], "count": 20}
  ],
  "unit": "tokens",
  "estimates": [
    {
      "members": ["/absolute/path/to/alpha", "/absolute/path/to/beta"],
      "action": "merge",
      "baseline_per_run": 1200,
      "candidate_per_run": 900,
      "expected_runs": 30,
      "build_cost": 1000,
      "evaluation_cost": 2000,
      "maintenance_cost": 500
    }
  ]
}
```

These example numbers are illustrative, not measurements. Costs share one explicit unit: `tokens`, `usd`, or `milliseconds`. All values are finite and nonnegative. Expected net savings are `(baseline_per_run - candidate_per_run) * expected_runs - build_cost - evaluation_cost - maintenance_cost`; the example gives 5,500 tokens under its assumptions.

Observed event counts and future `expected_runs` are different quantities. Do not extrapolate one into the other without an explicit forecast. Estimates remain labelled estimates, and missing costs remain unknown. File bytes describe packaging and cannot substitute for token or money measurements. A nonpositive forecast rejects that intervention under the supplied assumptions; unchanged evidence alone does not make its generation or evaluation free.

## Deliver this stage

Provide the selected plan, four alternatives for assessed groups, evidence and compatibility decisions, economic assumptions, and four distinct package states: selected, assessed keep, eligible but pending, and unassessed. `plan.coverage.single_skill_unassessed` separately identifies packages never checked internally; participation in a pair does not fill that gap. Do not report unfinished reviews as a high keep rate.

The allocation objective maximizes known positive net savings, then distinct package coverage among source-supported proposals, then source-backed content coverage, and finally favors lower action complexity. Without economics this is a library-coverage preference, not an economic optimum or a target intervention percentage. Verified source spans are unioned before counting normalized UTF-8 evidence bytes; these are opportunity coverage, not predicted runtime savings. The same source can participate in multiple non-conflicting reference extractions. An n-ary common reference can beat fragmented pairs without being penalized for producing fewer groups. Its reported optimum is for that objective among assessed proposals, not proof of library-wide economic optimality. The bounded search reports approximation at its node/option limit. Record the later source/combined/negative behavior checks.

This stage has no scheduler, source-update lifecycle, version switching or global installation. Those are separate work from selecting worthwhile targets.
