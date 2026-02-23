---
name: Feature Implementation
about: AI agent pipeline feature implementation task
title: '[P{phase}-{seq}] {feature-name}'
labels: ''
assignees: ''
---

## Feature

**Feature ID**: `{id}`
**Phase**: {phase}
**Layer**: `{layer}`

## Description

{description}

## Acceptance Criteria

- [ ] Implementation matches the spec in `shared/feature-specs/{feature}.md`
- [ ] All tests pass (coverage ≥ 80% lines, ≥ 70% branches)
- [ ] Code follows standards in `docs/standards/{layer}.md`
- [ ] No hardcoded secrets or API keys
- [ ] Documentation updated in `docs/features/{feature}.md`
- [ ] CHANGELOG updated under [Unreleased]

## Dependencies

{deps}

## Pipeline

Run with:
```
/pipeline-run {pipeline_id}
```

## References

- Docs: relevant sections in `docs/`
- API: `shared/api-contracts/`
- Design: `docs/14-tasarim.md`
