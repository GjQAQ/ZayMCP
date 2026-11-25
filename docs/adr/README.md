# Architecture Decision Records

This directory stores architecture decision records (ADRs) for choices that will affect the project for a long time. One decision per file. Do not rewrite a decision after it is accepted. To reverse it, add a new record and mark the old one as superseded.

## When to write one

Record a choice that affects the interface, process model, or external behavior. Do not record implementation details, temporary experiments, or facts that are obvious from the code.

## Files

- Path: `docs/adr/NNNN-short-title.md`. Numbers are four digits and only increase.
- Status: `Proposed`, `Accepted`, `Superseded`, or `Deprecated`. When a record is superseded, name the replacement at the top.
- Sections are fixed: Context, Decision, Considered options, Consequences.

## Template

```markdown
# NNNN. Title

- Status: Accepted
- Date: YYYY-MM-DD

## Context

The problem and the constraints.

## Decision

The chosen approach, stated in the affirmative.

## Considered options

Each rejected option and why it was rejected.

## Consequences

Constraints the decision imposes, and the capabilities it adds or removes.
```
