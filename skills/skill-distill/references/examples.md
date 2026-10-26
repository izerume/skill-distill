# Constructing combined examples

An example teaches a concrete execution pattern. Choose an input that exercises a meaningful interaction, then verify the output against all applicable source requirements. Keep independent single-source examples only when they demonstrate a branch the combined example does not cover.

## Example: factual fidelity and concise rewriting

Source requirements:

- Lead with the result and remove stacked hedging.
- Preserve numbers and evidence strength.
- A correlation cannot become a causal claim.
- Return the requested artifact without an editorial preface.

Input:

> Rewrite in one sentence: An observational study of 80 teams found an association between X and Y. This may perhaps possibly suggest that X could have some relation to Y.

Verified output:

> In an observational study of 80 teams, X was associated with Y.

Check: the number, study design, entities, and relationship are retained; the repeated uncertainty is removed; no cause, effect size, or new population is invented.

## Example: modes that change the output contract

If one source defines `audit`, a rewrite example alone does not demonstrate that capability. Add a compact audit case only when it clarifies the boundary:

Input:

> Audit, do not rewrite the paragraph: “We merely offer a preliminary attempt. The procedure applies only after calibration.”

Expected pattern:

> “We merely offer a preliminary attempt.” — DROP if it adds no evidence or scope; describe the actual work instead. Keep the calibration prerequisite because removing it changes when the procedure is valid.

This is an audit finding and a scoped suggestion, not a replacement paragraph. The conditional qualification is needed because the input does not say what the actual work achieved.

## Tool workflows

For a tool-dependent skill, record the input state, relevant tool call, resulting state, and the observable check. Verify the example through execution when feasible. A fabricated successful tool log is not an example to preserve.

Examples are teaching data. Hold out different task instances for final evaluation and avoid turning tested answers into general instructions. Preserve enough information to reproduce a failure without loading every historical trace at runtime.
