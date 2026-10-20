# Visual artifact report

Explain a visual workflow using labelled synthetic values

## Why

Compare explicit values while preserving sources and researcher control.

## What was built and checked

```json
{
  "nodes": 3,
  "edges": 2,
  "bounds": "passed",
  "node_overlap": "none",
  "edge_routing_and_labels": "require visual review",
  "preview_renderer": "PyMuPDF SVG converter; fonts may be substituted",
  "relation_semantics": "require researcher review; types are declarations"
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
