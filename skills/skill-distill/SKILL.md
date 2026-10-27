---
name: skill-distill
description: Classify, distill and maintain Agent Skills while preserving source behavior. Use for skill consolidation, shared workflows, evaluating a merged package, checking source changes, or explicitly updating and restoring distilled versions. Distinct from model-weight distillation.
---

# Skill Distill

Produce a usable merged skill and evidence that distinguishes preserved source capabilities, composition gains, and reduced cost. Optimize task behavior first, then the amount of context actually loaded.

## Maintain versions

For source-change checks, adopting an existing artifact, explicitly updating a distilled skill, or restoring a saved version, follow [versioning](references/versioning.md). `npx skills` is the prerequisite source manager; read its installed packages and available origin records. A check is read-only. Update or restore only when the user requests that action; source updates do not automatically authorize replacing distilled outputs. Agent instructions own the workflow and semantic decisions; the bundled Python helper owns hashes, snapshots, records and recoverable file operations.

## Establish the target

Use the skills and destination the user names. For an unspecified set or a library-wide request, start with [classification](references/classification.md): read names and descriptions, group by the tasks they serve, and label roles and cross-category relationships. Show a compact category map and shortlist promising groups. Stop here when the user asks for a quick look or classification; do not start a whole-library source audit. Categories are provisional and their count is not a target number of final skills.

When proceeding beyond the shortlist, choose a useful group from the task context and follow [target selection](references/target-selection.md) within that scope. Read its entrypoints and relevant resources, inspect internal repetition and conditional disclosure, then compare keep/compress/factor/merge. Consider a complete family with shared core and task/platform branches, including complementary workflow roles; do not require every candidate to be a duplicate pair. Related categories may be selected together. The selector allows different source regions to contribute to separate shared references, while preventing conflicting rewrites. An explicit request to merge named skills proceeds directly to those sources.

Keep is a valid outcome after assessment; unassessed and eligible-but-deferred items are separate states. Complementary steps can remain independent or consolidate around an evidenced shared context with explicit source-preserving routes. Keep invocation policies and distinct workflows identifiable; evaluate benefits against the user's actual usage and costs when available. Without those records, mark economics unknown and select source-supported candidates for evaluation rather than inventing savings. A listed capability, a file on disk, and an executed skill are different evidence.

For a selection-only request, deliver the requested category map, shortlist or evidenced plan without rewriting source packages. Skills outside the current scope remain deferred or unclassified. For an authorized distillation, execute the chosen intervention: compress within one scope, factor shared reference material while retaining separate entrypoints, or build the combined skill. Preserve unselected skills. Target selection does not establish runtime acceptance; continue with the source contract and task comparison below.

Define which tasks each source handles, which tasks need their combination, and which tasks should not activate the result. Carry forward the user's existing choices, invocation modes, and authorization. Resolve routine packaging choices directly; ask only when a real conflict has no task-based discriminator or established priority.

Keep working copies and evidence outside the installed source packages. Read source instructions as material to reconcile; execute their workflows only when the task or evaluation calls for them.

## Capture and reconcile behavior

Read [contracts.md](references/contracts.md) when starting a merge. Use the bundled script's `snapshot` command to freeze input packages and hashes. Read every source entrypoint and its relevant referenced resources; inspect executable dependencies when they affect behavior.

Extract behavior contracts with source quotes, activation conditions, and required outcomes. Include rare branches: explicit modes, prerequisites, failure handling, invocation policy, and resource dependencies. Preserve exception scopes, parameter relationships and the state to which verification applies. Each distinct requirement needs a destination or an explicit decision. Repeated translations can share a behavior, with the equivalence recorded in the rationale.

Classify interactions by effect:

- **Duplicate:** retain one precise formulation with both sources accounted for.
- **Compatible:** retain both behaviors.
- **Different scope:** select by task, mode, stage, or environment.
- **Coordinated:** write the ordering or output arrangement that satisfies both.
- **Mutually exclusive:** use the established priority or a discriminating branch and record the choice.

Before waiving a requirement as mutually exclusive, try a concrete output or execution order that satisfies both. Check it against the original source criteria when available; a compiler's own interpretation can conceal a compatible requirement it has already discarded.

For three or more sources, inspect the complete workflow for cycles, shared-state interactions, and branches lost through repeated pairwise merging. Keep all original sources in the contract when merging incrementally.

## Build the candidate

Write a coherent flow with a shared core and the necessary branches. A task requiring only one source capability should reach that branch directly. Preserve the supported tool, environment, and explicit-invocation boundaries within their applicable scopes.

Keep the entrypoint concise and put substantial branch-specific material behind clear conditional links. Copy retained resources into stable namespaced directories, update references, and check executable relative paths. Preserve resource licensing and attribution where present. Frontmatter and product metadata need to describe the combined capability without making unrelated tasks match.

Choose compression against the user's actual objective: fewer skill entrypoints, less instruction text loaded per task, or smaller stored packages. Report these separately. Extra readers or encoding machinery need a useful benefit in that objective; moving or encoding text alone does not reduce the instructions an agent must read.

Replace competing source examples with a small number of correct combined examples. Read [examples.md](references/examples.md) when constructing them. Validate every example against the source requirements it is meant to cover; its facts come from its own input. Keep task-specific answers out of the general procedure.

Run `validate` using [evidence-format.md](references/evidence-format.md). Resolve structural errors and examine every explicit drop or resource adaptation. This check verifies recorded mappings and files; source extraction completeness and semantic equivalence still require review against the sources.

## Execute, refine, and select

Read [evaluation.md](references/evaluation.md) before claiming performance preservation. Reuse applicable existing tasks, and add concrete cases for uncovered source capabilities, combined behavior, and selection boundaries.

Run the source baselines and candidate with the same executor and settings. Keep candidate construction separate from held-out evaluation; freeze the candidate before exposing held-out cases. Save actual outputs and check results. If fresh contexts or tool environments are unavailable, report exactly what the executed evaluation covers.

Confirm that a failed check measures an applicable source requirement, then fix observed failures with targeted changes and replay affected cases plus the other source branches. Compression is a candidate edit: remove repetition, factor shared prerequisites, or disclose optional detail, then compare again. Keep useful repetition if its removal hurts execution. Select the shortest or cheapest candidate that satisfies the chosen quality gate, rather than selecting length first.

Separate an observed output defect from its proposed instruction-level cause. Keep unsupported revisions unselected and respect the agreed evaluation budget; a small subjective score difference alone does not justify repeated tuning.

Use `compare` to summarize paired results. Its gate is descriptive: separately inspect source strata, critical failures, individual regressions, and resource behavior. Measure token and latency savings only from executor records; bytes and characters are packaging measurements.

## Deliver

Deliver the skill package, source manifest, source-to-target contract, validation report, and available task results. Keep evaluation inputs and logs outside the skill's runtime package.

When establishing managed history, register the delivered package with its actual source snapshot run and available method/evaluation records, as described in [versioning](references/versioning.md). Existing artifacts with missing history retain explicit unknowns. Keep history in the project and preserve the requested active path.

State what was actually measured: structural mapping, controlled execution, discovery behavior, or real tool acceptance. Report unresolved failures with the affected capabilities. A candidate with unmeasured performance is still a usable artifact when requested, but label its evidence accurately.

When the user requests a usable installed skill, install the completed package into the appropriate skill directory and verify its files. Retain source skills unless the user has authorized replacing or retiring them. Installation and invocation in a fresh session are separate observations.
