# Visual artifact report

Explain a visual workflow using labelled synthetic values

## Why

Compare explicit values while preserving sources and researcher control.

## What was built and checked

```json
{
  "panels": [
    {
      "kind": "line",
      "source": "data",
      "rows": 4,
      "missing_y_cells": 0,
      "statistics": "values and intervals read as supplied; no tests or CI estimation performed"
    },
    {
      "kind": "scatter",
      "source": "data",
      "rows": 4,
      "missing_y_cells": 0,
      "statistics": "values and intervals read as supplied; no tests or CI estimation performed"
    }
  ],
  "font": "Microsoft YaHei",
  "size_mm": [
    180,
    100
  ],
  "dpi": 160,
  "bounds_screen": "passed",
  "visual_review": "pending",
  "warnings": []
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
