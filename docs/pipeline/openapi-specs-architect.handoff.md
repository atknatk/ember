# Architect Handoff: OpenAPI Specs

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed
OpenAPI 3.1 YAML specification files for all 19 implemented API endpoints, organized into split path and schema files under `shared/api-contracts/`. Includes a drift-detection validation script that compares hand-written YAML specs against FastAPI's auto-generated OpenAPI schema, with CI integration to prevent spec drift.

## Key Decisions
- **Split file organization**: One YAML file per route group (auth, characters, chat, etc.) and one per schema domain, composed via `$ref` from a root `ember-api.yaml`. Rationale: a monolithic file would exceed 1000 lines and be difficult for mobile developers to navigate.
- **Validation, not generation**: The specs are hand-written for clarity and mobile-developer readability, then validated against FastAPI's auto-generated schema rather than generated from it. Rationale: auto-generated OpenAPI from FastAPI lacks SSE documentation, meaningful descriptions, and mobile-friendly organization.
- **SSE documentation pattern**: Since OpenAPI 3.1 cannot natively model SSE, the streaming endpoint is documented with `text/event-stream` content type and a prose description of the event format. The SSE event schemas (ChunkEvent, ActionEvent, DoneEvent, ErrorEvent) are defined separately for reference and potential code generation.
- **Dev-only validation dependencies**: pyyaml, openapi-spec-validator, and jsonref are added to dev dependencies only, not production requirements.

## Spec Location
`shared/feature-specs/openapi-specs.md`

## Assumptions Made
- All 19 endpoints listed in the spec are currently implemented and stable. The endpoint catalog was built by reading every route file in `backend/app/routes/`.
- The existing `.gitkeep` in `shared/api-contracts/` can be removed once real files are added.
- The `backend-ci.yml` workflow supports adding a new step without restructuring.

## Dependencies
- Requires: P01-10 (media-upload), P1.5-01 (rate-limiting-middleware) -- both already implemented
- Blocks: backend-dev (implements the YAML files and validation script)

## Next Steps
backend-dev should read the spec and implement: (1) all YAML spec files, (2) the validation script, (3) the CI step, and (4) the `openapi_tags` update to `main.py`.
