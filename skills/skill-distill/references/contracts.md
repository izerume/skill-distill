# Behavior contracts

The unit of preservation is a behavior under an activation condition. Split a sentence when it imposes independently testable behaviors. Keep a compound prerequisite intact when its conjunction matters.

For each source record:

- The source file and a verbatim quote identifying the instruction.
- The task, mode, phase, environment and relevant state in which it applies.
- The behavior and a way to observe its presence or violation.
- Its destination in the candidate, or an explicit conflict decision.

Use the smallest source and target spans that express the behavior. A pointer to an entire candidate section can pass a substring check while hiding an unrelated or weakened destination. Group repeated formulations by semantic requirement in the authoring notes; a large count of source lines is not a count of distinct preserved capabilities.

Inspect the source again after extraction. Rare instructions are easy to miss when most text repeats a shared principle. Metadata may carry a requirement absent from the body. Scripts can impose input formats, state changes, or recovery rules; use their real callers and outputs to interpret them.

Preserve relationships as well as individual values: which phase is faster, which step precedes another, and whether a limit is conditional. Two values can each satisfy a range while violating their required ordering. Make that relationship observable in the contract and its examples.

Where a source requires fresh verification, record the state it verifies. Evidence from an earlier implementation does not establish the result after new edits. Interpret a suggestion to avoid redundant checks in that state; an explicit user prohibition on execution still controls, and the blocked verification remains unverified.

## Interaction decisions

Determine whether two instructions can hold under the **same conditions**. Similar wording is a candidate for analysis, not a merge decision.

| Situation | Decision |
| --- | --- |
| A and B both require factual fidelity | One common rule; map both sources |
| A applies to code, B to prose | Preserve separate conditional branches |
| A build recipe permits a layout-animation exception; an audit requires only transform/opacity | Keep the exception in build mode; preserve the stricter audit rule |
| One instruction requires a final signature; another requires a reference trailer near the end | Arrange both explicitly if the wording permits it |
| A requires JSON and B requires prose for the same output | Apply the user's format/priority or expose a real mode choice |
| Audit identifies findings, rewrite returns an edited artifact | Make mode selection precede editing |

Record uncertainty locally. If an abstraction's equivalence is uncertain, retaining the specific clauses is a valid candidate. Favor source-supported routing over inventing a broader universal rule.

A shared reference must preserve each clause's scope. Place a mode-specific exception beside its condition; do not turn it into a general default that weakens another mode. Apply only the source's actual restrictions, rather than extending the stricter mode to every task.

For position, order, and shared-budget requirements, construct a joint arrangement before assigning priority. An exact second-line field can coexist with another field allowed anywhere in the top metadata region. If both require the exact same exclusive position, priority is necessary. When phrases such as "right under" are ambiguous, record the interpretation accepted by the original checker or task specification; do not silently relax the source to make a candidate pass.

Resolve both the syntax and allowed content of a winning output slot. If the primary requires a heading containing only the title, keep a ticket identifier from a losing title format in separate metadata. State that placement in the execution flow; retaining the winning source sentence alone may still let the losing format leak into the slot.

Validate teaching examples against source-owned checks, where available, rather than only a checklist derived from the rewritten skill. Keep any source-example feedback and repairs separate from held-out execution. Structural quote coverage and a compiler's self-check can both pass while a compatible source behavior has been lost.

For multi-source merges, track original rule IDs throughout. A chain A+B → AB, AB+C → ABC can otherwise hide rules already lost in AB. Inspect order constraints globally: pairwise compatibility does not establish that the entire sequence is executable.

## Resources and discovery

Every snapshotted auxiliary file needs a `copy`, `adapt`, or `omit` decision. A byte-preserving copy proves file retention, not that its callers still work. For renamed files, check Markdown references, script imports, template paths, and working-directory assumptions relevant to the actual package.

Regenerate `agents/openai.yaml` deliberately. Preserve explicit-only invocation when a source capability requires it, potentially by keeping that capability as a separately invoked branch or companion skill. A merged description's broader reach is a behavior change to evaluate. Keep unrelated capabilities separate when their invocation policies cannot be represented faithfully by one entrypoint.

The helper's source-to-target quote checks establish that a recorded rule has a recorded destination. They do not establish that all source rules were extracted, that the destination entails the source, or that the executor follows it.
