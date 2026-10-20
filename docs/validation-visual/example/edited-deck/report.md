# Visual artifact report

Exact text replacement software fixture

## Why

Check exact edits while preserving other presentation parts.

## What was built and checked

```json
{
  "edited_parts": [
    "ppt/slides/slide1.xml"
  ],
  "edits": 1,
  "unchanged_parts": "original uncompressed bytes retained",
  "office_render": "not_run",
  "visual_review": "pending; replacement text can change wrapping"
}
```

## Researcher decisions

- Does the framing express the intended scientific question?
- Are the claims, alternatives, uncertainty and limitations represented accurately?
- Is the selected visual encoding and information density appropriate for this audience?
- What should be revised, explained, retained or stopped?

Human review: pending. No approval was generated. File checks do not establish scientific correctness.
Use the managed stage report and stage-feedback for review, branching and adoption.

## Rebuild

spec.json binds copies in inputs/; run the recorded builder against this spec with a new output directory.
Use the recorded code and dependency versions; fonts are identified by hash and are not redistributed.
This package contains copies of supplied sources. Review them before sharing the package.
