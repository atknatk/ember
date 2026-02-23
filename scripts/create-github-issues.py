#!/usr/bin/env python3
"""Create all GitHub milestones, labels, and issues for Ember repo."""
import json
import subprocess
import sys
from pathlib import Path

REPO = "atknatk/ember"
SCRIPT_DIR = Path(__file__).parent
QUEUE = SCRIPT_DIR / "feature-queue.jsonl"
ISSUE_MAP = SCRIPT_DIR / "issue-map.json"


def gh(*args, check=True):
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        # Non-fatal: print warning but continue
        pass
    return result.stdout.strip(), result.returncode


def create_milestone(title: str, description: str) -> int:
    """Create a milestone and return its number."""
    out, code = gh(
        "api", f"repos/{REPO}/milestones",
        "--method", "POST",
        "-f", f"title={title}",
        "-f", f"description={description}",
        "--jq", ".number",
    )
    if out and code == 0:
        print(f"  Created milestone: {title} → #{out}")
        return int(out)
    # Maybe already exists — fetch it
    out2, _ = gh(
        "api", f"repos/{REPO}/milestones",
        "--jq", f".[] | select(.title == \"{title}\") | .number",
    )
    if out2:
        print(f"  Found existing milestone: {title} → #{out2}")
        return int(out2)
    print(f"  WARN: Could not create milestone: {title}")
    return 0


def create_label(name: str, color: str, description: str):
    gh("label", "create", name,
       "--color", color,
       "--description", description,
       "--repo", REPO,
       "--force",
       check=False)
    print(f"  Label: {name}")


def create_issue(title: str, body: str, labels: list[str], milestone_title: str) -> int:
    label_str = ",".join(labels)
    args = [
        "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--body", body,
        "--label", label_str,
    ]
    if milestone_title:
        args += ["--milestone", milestone_title]
    out, code = gh(*args)
    # gh issue create returns URL like: https://github.com/owner/repo/issues/42
    if out and code == 0 and "/issues/" in out:
        return int(out.rstrip().split("/issues/")[-1])
    return 0


def main():
    if not QUEUE.exists():
        print(f"ERROR: {QUEUE} not found")
        sys.exit(1)

    features = []
    with open(QUEUE) as f:
        for line in f:
            line = line.strip()
            if line:
                features.append(json.loads(line))

    print(f"Loaded {len(features)} features from feature-queue.jsonl\n")

    # ── Milestones ─────────────────────────────────────────────────────────────
    print("=== Creating GitHub Milestones ===")
    phase_info = {
        1:  ("Faz 1: Backend Temeli",          "FastAPI scaffold, DB schema, auth, chat streaming, memory endpoints"),
        2:  ("Faz 2: Proaktif Bildirimler",     "Activity tracking, FCM push, APScheduler cron, proactive messages"),
        3:  ("Faz 3: iOS Native App",           "SwiftUI app, auth, onboarding, home, chat (SSE), memories, profile, FCM"),
        4:  ("Faz 4: Android Native App",       "Jetpack Compose app, auth, onboarding, home, chat (SSE), memories, profile, FCM"),
        5:  ("Faz 5: Sesli Deneyim",            "STT (Whisper), TTS (ElevenLabs+Polly), voice recording & playback"),
        6:  ("Faz 6: Cihaz Entegrasyonu",       "Alarm, calendar, call log — intent extraction via Claude Haiku"),
        7:  ("Faz 7: Fotoğraf ve Medya",        "Photo sharing, Claude vision analysis, food calorie estimation"),
        8:  ("Faz 8: Partner Bağlantısı",       "Partner invite/accept, anonymous progress sharing"),
        9:  ("Faz 9: Karakter Sistemi",         "Multi-character templates (companion, therapist, coach, teacher, custom)"),
        10: ("Faz 10: Fitness Entegrasyonu",    "Body measurements, weight tracking chart, ExerciseDB proxy"),
        11: ("Faz 11: Cila ve Yayın",           "Polish, accessibility, localization (TR+EN), App Store + Play Store"),
        12: ("Faz 12: Gerçek Zamanlı Ses",      "LiveKit Agents real-time voice call (Deepgram + Claude Haiku + ElevenLabs)"),
    }
    milestone_titles: dict[int, str] = {}
    for phase, (title, desc) in phase_info.items():
        create_milestone(title, desc)
        milestone_titles[phase] = title

    # ── Labels ─────────────────────────────────────────────────────────────────
    print("\n=== Creating GitHub Labels ===")
    phase_colors = {
        1: "4B0082", 2: "5B1A9E", 3: "6B2AB8", 4: "7B3AD2",
        5: "8B4AEC", 6: "9B5AF6", 7: "AB6AFF", 8: "BB7AFF",
        9: "CB8AFF", 10: "DB9AFF", 11: "EBaeff", 12: "FBbaff",
    }
    for phase, color in phase_colors.items():
        create_label(f"phase:{phase}", color, f"Faz {phase}")

    layer_labels = [
        ("layer:backend",   "0075CA", "Python/FastAPI backend"),
        ("layer:ios",       "E4E669", "iOS Swift/SwiftUI"),
        ("layer:android",   "0E8A16", "Android Kotlin/Compose"),
        ("layer:mobile",    "F9D0C4", "iOS + Android both"),
        ("layer:fullstack", "D93F0B", "Backend + iOS + Android"),
    ]
    for name, color, desc in layer_labels:
        create_label(name, color, desc)

    type_labels = [
        ("type:model",       "BFD4F2", "Data model / DB schema"),
        ("type:api",         "BFDFFF", "API endpoint"),
        ("type:ui",          "FFE0B2", "UI screen / component"),
        ("type:service",     "D4EDDA", "Business logic service"),
        ("type:infra",       "F0F0F0", "Infrastructure / DevOps"),
        ("type:integration", "FFF3CD", "Third-party integration"),
    ]
    for name, color, desc in type_labels:
        create_label(name, color, desc)

    create_label("agent:pipeline", "1D76DB", "AI agent pipeline PR — auto-merge")

    # ── Issues ─────────────────────────────────────────────────────────────────
    print("\n=== Creating GitHub Issues ===")
    issue_map: dict[str, int] = {}

    for feat in features:
        fid = feat["id"]
        phase = feat["phase"]
        layer = feat["layer"]
        name = feat["name"]
        pipeline_id = feat["pipeline_id"]
        deps = feat.get("deps", [])
        desc = feat["description"]

        title = f"[{fid}] {name}"
        deps_str = ", ".join(deps) if deps else "None"

        body = f"""## Feature

**Feature ID**: `{fid}`
**Phase**: {phase}
**Layer**: `{layer}`
**Pipeline ID**: `{pipeline_id}`

## Description

{desc}

## Dependencies

{deps_str}

## Acceptance Criteria

- [ ] Implementation matches spec in `shared/feature-specs/{name}.md`
- [ ] Tests pass (≥80% line coverage, ≥70% branch coverage)
- [ ] Code follows `docs/standards/{layer}.md`
- [ ] No hardcoded secrets or API keys
- [ ] Documentation updated in `docs/features/{name}.md`
- [ ] CHANGELOG updated under [Unreleased]

## How to Implement

```bash
/pipeline-run {pipeline_id}
```

## References

- Architecture: `docs/03-mimari.md`
- API Contracts: `shared/api-contracts/`
- Data Model: `docs/04-veri-api.md`
- Design System: `docs/14-tasarim.md`
- AI & Memory: `docs/05-ai-bellek.md`
- Standards: `docs/standards/{layer}.md`"""

        labels = [f"phase:{phase}", f"layer:{layer}"]
        milestone_title = milestone_titles.get(phase, "")

        issue_num = create_issue(title, body, labels, milestone_title)
        if issue_num:
            print(f"  ✓ #{issue_num}: {title}")
            issue_map[fid] = issue_num
        else:
            print(f"  ✗ FAILED: {title}")

    # ── Save issue map ──────────────────────────────────────────────────────────
    with open(ISSUE_MAP, "w") as f:
        json.dump(issue_map, f, indent=2)

    print(f"\n=== Done ===")
    print(f"Issues created: {len(issue_map)} / {len(features)}")
    print(f"Issue map: {ISSUE_MAP}")


if __name__ == "__main__":
    main()
