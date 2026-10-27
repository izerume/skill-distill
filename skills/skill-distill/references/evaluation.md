# Evaluation and candidate selection

Choose an evaluation proportional to the merge. The central question is whether each source capability survives on its own tasks and whether the composition helps on combined tasks.

## Baselines and task slices

Use the source skill alone on its native tasks. On combined tasks, compare against the user's current combination strategy; optionally add a correctly staged source workflow as a stronger baseline. A simple one-call merge is useful when testing whether a more elaborate compiler earns its cost.

Keep A-only, B-only, combined, and boundary/negative tasks separately identifiable. For more sources, retain a slice for each relevant capability rather than aggregating them all. Add cases for specialized modes and prerequisites that generic success tests would miss.

For a gain study, calibrate task difficulty on development cases at the intended executor and budget. A ceiling baseline leaves little room to distinguish methods. Retain all screened results, record the selection rule, and freeze the holdout before selecting the final candidate; never keep only favorable held-out outcomes.

When attributing a gain, separate removing old examples, resolving true conflicts, adding a concrete joint workflow, and adding a new example. Freeze the exact differences between variants. A useful sequential comparison is original skills → original rules without examples → resolved rules → explicit coordination → coordination plus a verified example. Packaging and length can change alongside resolution, so describe that comparison as a combined treatment rather than attributing it to a single operation.

Reuse known cases for development. Create held-out task instances before selecting the final candidate and keep them unavailable to its author. Once held-out failures guide an edit, those cases become regression/development evidence; use a new holdout for another generalization claim.

## Quick smoke checks

When the user asks for a quick check, use a small set of representative tasks covering the selected source modes and one important boundary, such as preserving user edits or waiting for a selection. A few cases per condition, batched in one executor context, are sufficient for this requested smoke check; use matching executor settings and retain actual replies and file artifacts. Stop after those cases pass. Fix and replay only an observed failure instead of automatically expanding into a full benchmark.

Report the case count and any regressions as smoke evidence. Keep package-size measurements separate from loaded tokens or cost, and reserve broad performance-preservation claims for broader evaluation when requested.

## Execution

Use the same executor model, options, tools, maximum attempts, and context conditions for paired comparisons. Fresh conversations per task give the cleanest isolation. If using one batch per condition, label it as a batch pilot: earlier examples may influence later outputs. Never report the number of outputs as the number of independent model calls.

Provide executors with the applicable skill and the task, not the answer key or hypothesized failure. Keep output generation separate from grading. Preserve raw outputs, the exact prompts or prompt hashes, skill hashes, run/task IDs, and available usage records. Missing token or latency measurements remain missing.

Before dispatch, reconcile each arm's supplied files with its intended frozen package, including auxiliary resources. Record intentional exclusions. Missing intended source material invalidates that pair as a full-source comparison; keep its outputs without using them to establish a candidate gain.

For tool workflows, run in bounded task workspaces and judge resulting artifacts or state. Tool-free text execution does not establish tool reliability. Testing a forced-loaded skill does not establish discovery recall; evaluate selection separately with a catalog and positive/negative requests when needed.

## Grading

Use executable checks for exact facts, schemas, artifacts, or behavior. Use a fixed rubric for meaning and quality where a mechanical test is insufficient. A successful output must satisfy the requested task, not merely contain expected keywords. Judge semantically equivalent wording equivalently.

Record each check, its result, and a short piece of evidence or rationale. Mark meaning-changing errors as critical: invented facts, lost prerequisites, incorrect mode, broken resources, or changed side effects. Identify cases by stable IDs. Keep the source-derived checklist fixed between baseline and candidate.

Before editing behavior for a failed check, confirm that its source condition applies. A checker that always requires rounding does not measure a rule limited to monetary or averaged aggregates on a count-only query. Preserve the frozen score, record the mismatch separately, and base a semantic assessment on the source condition. Do not add unrelated operations merely to satisfy such a check.

For subjective evaluation, hide method identity and randomize order where feasible. If the author also grades, disclose that dependency; deterministic results and an independent executor still have value, but do not make the grading independent.

Keep a visible output defect, a score difference and a suspected cause separate. When investigating a small subjective difference, predeclare a bounded comparison and control relevant inputs such as task data and design direction. If the comparison does not support the proposed cause, leave it unresolved. Do not revise the gate after seeing scores, keep generating until one result wins, or treat an inconclusive difference as proof of equivalence.

## Gates and interpretation

The helper compares fully correct outputs and individual check rates in each stratum and lists paired gains and regressions. `observed_gate_passed` requires no decline in those per-stratum rates and no candidate critical failures. Review individual regressions even when gains offset them.

This gate is descriptive. Zero failures on a small sample is evidence about those cases, not a proof of distribution-wide equivalence. For a statistical claim, predefine the noninferiority margin and independent sampling unit, use paired intervals at task/cluster level, and account for repeated candidate selection. A nonsignificant difference is not evidence of equivalence.

## Feedback and cost

Change the instruction responsible for an observed failure, then replay that case and the other source slices. Preserve the earlier candidate if a new edit regresses. Stop when the requested gate is met or the remaining failure requires unavailable tools, a real policy choice, or additional data; deliver the concrete candidate and evidence at that boundary.

After quality stabilizes, test a smaller candidate. Measure actual loaded tokens, tool calls, and attempts; a reduction in file bytes alone is a size result. Count reference reads and amortize offline compilation separately. Compare equal execution budgets before attributing gains to the skill.
