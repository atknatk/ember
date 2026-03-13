# Architect Handoff: Android Profile Screen

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Summary

Designed the Android Profile screen (P04-07) as a direct Android counterpart to the iOS ProfileView (P03-09). The screen replaces the existing placeholder ProfileScreen with a production settings hub.

## Key Decisions

- Profile header with Coil-loaded avatar or gradient initial circle
- Timezone picker uses ModalBottomSheet with searchable list
- Delete account requires typing "DELETE MY ACCOUNT" in an AlertDialog
- Notification toggles are UI-only placeholders (no API call)
- Sign out delegates to AuthRepository, navigates via shouldSignOut StateFlow

## Spec Location

`shared/feature-specs/android-profile.md`
