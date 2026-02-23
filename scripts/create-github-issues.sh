#!/usr/bin/env bash
# create-github-issues.sh — Create all GitHub milestones, labels, and issues
# Usage: ./scripts/create-github-issues.sh
# Requires: gh (GitHub CLI), jq

set -e
REPO="atknatk/ember"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE="$SCRIPT_DIR/feature-queue.jsonl"
ISSUE_MAP="$SCRIPT_DIR/issue-map.json"

if [ ! -f "$QUEUE" ]; then
  echo "ERROR: $QUEUE not found"
  exit 1
fi

echo "=== Creating GitHub Milestones ==="

declare -A MILESTONE_IDS

create_milestone() {
  local phase=$1
  local title=$2
  local desc=$3
  local id
  id=$(gh api repos/$REPO/milestones \
    --method POST \
    -f title="$title" \
    -f description="$desc" \
    --jq '.number' 2>/dev/null || echo "")
  if [ -z "$id" ]; then
    # Milestone might already exist, fetch it
    id=$(gh api repos/$REPO/milestones --jq ".[] | select(.title == \"$title\") | .number" 2>/dev/null || echo "")
  fi
  echo "  Milestone: $title → #$id"
  MILESTONE_IDS[$phase]=$id
}

create_milestone 1  "Faz 1: Backend Temeli"          "FastAPI scaffold, DB schema, auth, chat streaming, memory endpoints"
create_milestone 2  "Faz 2: Proaktif Bildirimler"     "Activity tracking, FCM push, APScheduler cron, proactive messages"
create_milestone 3  "Faz 3: iOS Native App"           "SwiftUI app, auth, onboarding, home, chat (SSE), memories, profile, FCM"
create_milestone 4  "Faz 4: Android Native App"       "Jetpack Compose app, auth, onboarding, home, chat (SSE), memories, profile, FCM"
create_milestone 5  "Faz 5: Sesli Deneyim"            "STT (Whisper), TTS (ElevenLabs+Polly), voice recording & playback on iOS+Android"
create_milestone 6  "Faz 6: Cihaz Entegrasyonu"       "Alarm, calendar, call log integration — intent extraction via Claude Haiku"
create_milestone 7  "Faz 7: Fotoğraf ve Medya"        "Photo sharing, Claude vision analysis, food calorie estimation"
create_milestone 8  "Faz 8: Partner Bağlantısı"       "Partner invite/accept, anonymous progress sharing"
create_milestone 9  "Faz 9: Karakter Sistemi"         "Multi-character templates (companion, therapist, coach, teacher, custom)"
create_milestone 10 "Faz 10: Fitness Entegrasyonu"    "Body measurements, weight tracking chart, ExerciseDB proxy"
create_milestone 11 "Faz 11: Cila ve Yayın"           "Polish, accessibility, localization (TR+EN), App Store + Play Store submission"
create_milestone 12 "Faz 12: Gerçek Zamanlı Ses"      "LiveKit Agents real-time voice call (Deepgram + Claude Haiku + ElevenLabs)"

echo ""
echo "=== Creating GitHub Labels ==="

create_label() {
  local name=$1
  local color=$2
  local desc=$3
  gh label create "$name" --color "$color" --description "$desc" --repo $REPO --force 2>/dev/null || true
  echo "  Label: $name"
}

# Phase labels (purple shades)
create_label "phase:1"  "4B0082" "Faz 1: Backend Temeli"
create_label "phase:2"  "5B1A9E" "Faz 2: Proaktif Bildirimler"
create_label "phase:3"  "6B2AB8" "Faz 3: iOS Native App"
create_label "phase:4"  "7B3AD2" "Faz 4: Android Native App"
create_label "phase:5"  "8B4AEC" "Faz 5: Sesli Deneyim"
create_label "phase:6"  "9B5AF6" "Faz 6: Cihaz Entegrasyonu"
create_label "phase:7"  "AB6AFF" "Faz 7: Fotoğraf ve Medya"
create_label "phase:8"  "BB7AFF" "Faz 8: Partner Bağlantısı"
create_label "phase:9"  "CB8AFF" "Faz 9: Karakter Sistemi"
create_label "phase:10" "DB9AFF" "Faz 10: Fitness Entegrasyonu"
create_label "phase:11" "EBaaFF" "Faz 11: Cila ve Yayın"
create_label "phase:12" "FBbaFF" "Faz 12: Gerçek Zamanlı Ses"

# Layer labels
create_label "layer:backend"   "0075CA" "Python/FastAPI backend"
create_label "layer:ios"       "E4E669" "iOS Swift/SwiftUI"
create_label "layer:android"   "0E8A16" "Android Kotlin/Compose"
create_label "layer:mobile"    "F9D0C4" "iOS + Android both"
create_label "layer:fullstack" "D93F0B" "Backend + iOS + Android"

# Type labels
create_label "type:model"       "BFD4F2" "Data model / DB schema"
create_label "type:api"         "BFDFFF" "API endpoint"
create_label "type:ui"          "FFE0B2" "UI screen / component"
create_label "type:service"     "D4EDDA" "Business logic service"
create_label "type:infra"       "F0F0F0" "Infrastructure / DevOps"
create_label "type:integration" "FFF3CD" "Third-party integration"

# Pipeline label
create_label "agent:pipeline"   "1D76DB" "AI agent pipeline PR — auto-merge"

echo ""
echo "=== Creating GitHub Issues ==="

# Initialize issue map
echo "{}" > "$ISSUE_MAP"

while IFS= read -r line; do
  [ -z "$line" ] && continue

  ID=$(echo "$line" | jq -r '.id')
  PHASE=$(echo "$line" | jq -r '.phase')
  LAYER=$(echo "$line" | jq -r '.layer')
  NAME=$(echo "$line" | jq -r '.name')
  PIPELINE_ID=$(echo "$line" | jq -r '.pipeline_id')
  DEPS=$(echo "$line" | jq -r '.deps | join(", ")')
  DESC=$(echo "$line" | jq -r '.description')

  TITLE="[$ID] $NAME"

  # Build deps section
  if [ -z "$DEPS" ] || [ "$DEPS" = "" ]; then
    DEPS_SECTION="None"
  else
    DEPS_SECTION="$DEPS"
  fi

  BODY="## Feature

**Feature ID**: \`$ID\`
**Phase**: $PHASE
**Layer**: \`$LAYER\`
**Pipeline ID**: \`$PIPELINE_ID\`

## Description

$DESC

## Dependencies

$DEPS_SECTION

## Acceptance Criteria

- [ ] Implementation matches spec in \`shared/feature-specs/$NAME.md\`
- [ ] Tests pass (≥80% line coverage, ≥70% branch coverage)
- [ ] Code follows \`docs/standards/$LAYER.md\`
- [ ] No hardcoded secrets or API keys
- [ ] Documentation updated in \`docs/features/$NAME.md\`
- [ ] CHANGELOG updated under [Unreleased]

## How to Implement

\`\`\`bash
/pipeline-run $PIPELINE_ID
\`\`\`

## References

- Architecture: \`docs/03-mimari.md\`
- API Contracts: \`shared/api-contracts/\`
- Data Model: \`docs/04-veri-api.md\`
- Design System: \`docs/14-tasarim.md\`
- AI & Memory: \`docs/05-ai-bellek.md\`"

  MILESTONE_NUM=${MILESTONE_IDS[$PHASE]}

  ISSUE_NUM=$(gh issue create \
    --repo "$REPO" \
    --title "$TITLE" \
    --body "$BODY" \
    --label "phase:$PHASE,layer:$LAYER" \
    --milestone "$MILESTONE_NUM" \
    --jq '.number' 2>/dev/null || echo "")

  if [ -n "$ISSUE_NUM" ]; then
    echo "  ✓ #$ISSUE_NUM: $TITLE"
    # Update issue map
    TMP=$(cat "$ISSUE_MAP" | jq --arg id "$ID" --argjson num "$ISSUE_NUM" '. + {($id): $num}')
    echo "$TMP" > "$ISSUE_MAP"
  else
    echo "  ✗ FAILED: $TITLE"
  fi

done < "$QUEUE"

echo ""
echo "=== Done ==="
echo "Issue map saved to: $ISSUE_MAP"
echo "Total issues created: $(cat "$ISSUE_MAP" | jq 'keys | length')"
