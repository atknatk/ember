# Architect Handoff: Android Scaffold

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Feature
- **ID**: P04-01
- **Name**: android-scaffold
- **Layer**: android

## Design Decisions

1. **Package name**: `ai.ember.app` (matching standards doc convention)
2. **Dark-only theme**: No light theme variant — Ember is dark-first per docs/14-tasarim.md
3. **Color tokens match iOS exactly**: All hex values from Color+Ember.swift preserved
4. **Typography maps to Material 3 slots**: iOS font scale mapped to closest Material 3 typography slots
5. **Bottom tabs match iOS**: Home, Memories, Profile — same order, equivalent icons
6. **Hilt DI from day one**: Application and Activity annotated for Hilt
7. **Version catalog**: All dependencies managed via gradle/libs.versions.toml
8. **Placeholder screens**: Each tab gets a minimal composable — feature content in later phases

## Spec Location
- `shared/feature-specs/android-scaffold.md`

## Deviations
- None. Follows docs/14-tasarim.md and iOS implementation exactly.
