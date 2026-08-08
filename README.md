<p align="center">
  English | <a href="README_ZH.md">简体中文</a>
</p>

<h1 align="center">AppleWatchChallengeRadar</h1>

<p align="center">
  Dual-source Apple Watch Limited Edition Challenge monitoring, ICS feeds, and change notifications
</p>

<p align="center">
  <a href="https://github.com/skyrocketingHong/AppleWatchChallengeRadar/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/skyrocketingHong/AppleWatchChallengeRadar/ci.yml?branch=main&amp;label=CI" alt="CI status"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11 or later">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue" alt="AGPL-3.0 license"></a>
</p>

AppleWatchChallengeRadar monitors Apple MobileAsset definitions for Apple Watch Limited Edition Challenges. It keeps the Current and Legacy sources independent, normalizes and merges their results into SQLite, publishes stable ICS calendar feeds, and notifies you when a challenge is added, materially updated, or withdrawn before it starts.

The service is designed for Debian or Ubuntu: a systemd timer runs a short-lived update task, and an existing Caddy instance can serve the generated calendars. It does not require Docker, a separate database service, or a long-running Python web process.

## Highlights

- Processes the Current and Legacy MobileAsset sources independently, so one failed source never overwrites successful data from the other.
- Represents challenges with a canonical model for identifiers, date ranges, regional availability, completion rules, and triggers.
- Merges fields with explicit precedence: manual overrides → Current → Legacy → derived values, while recording conflicts.
- Renders supported Predicate rules into readable Chinese challenge conditions, such as “complete at least 20 minutes of any workout.”
- Publishes six stable feeds: <code>all</code>, <code>history</code>, <code>upcoming</code>, <code>global</code>, <code>cn</code>, and <code>us</code>.
- Uses atomic ICS writes, stable UIDs, and incrementing SEQUENCE values to work reliably with calendar clients.
- Deduplicates notifications with a persistent <code>event_key</code>; Bootstrap records history without sending historical alerts.
- Supports generic Webhook, Bark, and ntfy providers. A provider failure does not stop the update pipeline.

## Apple Data Sources

The runtime uses the following public Apple MobileAsset catalog endpoints. They are configuration defaults, not a documented Apple public API; Apple may change their schema, availability, or contents without notice.

| Source | Asset type | Runtime catalog |
| :--- | :--- | :--- |
| Legacy | <code>com.apple.MobileAsset.Activity.Achievements</code> | [Activity.Achievements catalog](https://mesu.apple.com/assets/com_apple_MobileAsset_Activity_Achievements/com_apple_MobileAsset_Activity_Achievements.xml) |
| Current | <code>com.apple.MobileAsset.ActivityChallengeAssets</code> | [ActivityChallengeAssets catalog](https://mesu.apple.com/assets/com_apple_MobileAsset_ActivityChallengeAssets/com_apple_MobileAsset_ActivityChallengeAssets.xml) |

The Current source provides the newer challenge definitions. The Legacy source preserves older records and is intentionally not parsed as if it had the Current source schema.

## Design Principles

- **Independent source adapters.** Current and Legacy have separate adapters and schemas; source-specific behavior stays out of calendar, storage, and notification code.
- **Canonical identity before output.** Both sources are normalized to one stable <code>canonical_id</code>. Identifier aliases are explicit configuration, never fuzzy title matching.
- **Traceable merge policy.** The precedence order is manual override → Current → Legacy → derived value. Disagreements are retained as conflicts rather than silently overwritten.
- **Two-level change detection.** Asset changes are detected per source first; only a changed canonical challenge can affect ICS files or notifications.
- **Failure is not deletion.** A source may mark records removed only after that source fetched and parsed successfully. A failed request leaves prior records intact.
- **Preserve uncertainty.** Unknown Predicate rules, workout types, and regional scope are retained as raw or <code>unknown</code>; unknown scope is never promoted to global.
- **Calendar correctness.** ICS writes use a temporary file, validation, <code>fsync</code>, and atomic replacement. UIDs remain stable while meaningful changes increment SEQUENCE.
- **Separate discovery from reminders.** Notifications announce source-side discovery or change, while ICS alarms remind subscribers that a challenge is approaching. Bootstrap establishes a baseline without historical alert spam.

## Planning and Research References

Only the two MESU catalogs above are runtime inputs. The links below are planning, reverse-engineering, and historical cross-check references retained for traceability; they are not runtime dependencies, and third-party sources do not imply Apple affiliation or endorsement.

| Category | References retained from planning |
| :--- | :--- |
| Apple platform and asset research | [The Apple Wiki — asset types](https://theapplewiki.com/wiki/List_of_asset_types), [The Apple Wiki — MobileAssets](https://theapplewiki.com/wiki/MobileAssets), [NewOSXBook — activityawardsd entitlements](https://newosxbook.com/ent.php?exec=activityawardsd), [Apple Developer — HKWorkoutActivityType](https://developer.apple.com/documentation/healthkit/hkworkoutactivitytype), [Apple Support — Activity ring goals](https://support.apple.com/guide/watch/adjust-your-activity-ring-goals-apd29b30023c/watchos) |
| Official challenge announcements | [Apple Newsroom — Get active with Apple Watch (2025)](https://www.apple.com/newsroom/2025/04/get-active-with-apple-watch/), [Apple Newsroom — New Year (2026)](https://www.apple.com/newsroom/2026/01/stay-active-in-the-new-year-with-apple-watch/) |
| Challenge history cross-checks | [9to5Mac — Yoga Day 2026](https://9to5mac.com/2026/06/16/this-sundays-apple-watch-activity-challenge-celebrates-international-day-of-yoga/), [9to5Mac — National Fitness Day 2026](https://9to5mac.com/2026/08/04/apple-watch-national-fitness-day-challenge-returns-this-weekend/), [MacRumors Activity Challenge guide](https://www.macrumors.com/guide/activity-challenge/), [Kyle Seth Gray’s special-achievement archive](https://kylesethgray.com/a-list-of-apple-watch-special-achievements/), [Peter Wunder’s achievements archive](https://projects.peterwunder.de/achievements/) |

## Technology

| Area | Main technologies |
| :--- | :---------------- |
| Runtime | Python 3.11+ |
| Sources | Apple MobileAsset MESU, Current and Legacy adapters |
| Storage | SQLite |
| Calendar output | icalendar, RFC 5545 |
| Configuration | YAML and environment-variable overrides |
| Scheduling and hosting | systemd timer and Caddy |
| Quality | pytest and GitHub Actions |

## Requirements

Local development requires Python 3.11 or later and network access to Apple MESU. Production deployments are intended for Debian or Ubuntu with Conda, systemd, and Caddy.

## Quick Start

~~~bash
git clone https://github.com/skyrocketingHong/AppleWatchChallengeRadar.git
cd AppleWatchChallengeRadar

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

python -m pytest
challenge-radar bootstrap --state-dir ./var --output-dir ./output
~~~

The first <code>bootstrap</code> creates a local baseline and ICS feeds without sending notifications for historical challenges. Use <code>update</code> for subsequent incremental checks.

Alternatively, create the provided Conda environment:

~~~bash
conda env create -f environment.yml
conda activate apple-watch-challenge-radar
python -m pip install -e ".[dev]"
~~~

## Commands

| Command | Purpose |
| :--- | :--- |
| <code>challenge-radar bootstrap</code> | Perform the first full import without historical notifications |
| <code>challenge-radar update</code> | Fetch, parse, merge, persist, notify, and regenerate affected feeds |
| <code>challenge-radar generate</code> | Regenerate ICS files from SQLite without network access |
| <code>challenge-radar status</code> | Show source health and challenge statistics |
| <code>challenge-radar inspect-sources</code> | Show discovery results for both source catalogs |

<code>bootstrap</code> and <code>update</code> accept <code>--state-dir</code> and <code>--output-dir</code> for local runs.

## Architecture

~~~text
Apple MobileAsset MESU
        │
        ├── Legacy Source ──► Legacy Adapter
        └── Current Source ─► Current Adapter
                                 │
                    Canonical Normalize / Alias / Merge
                                 │
                              SQLite
                         ┌───────┴────────┐
                         ▼                ▼
                    ICS Generator   Notification Manager
                         │                │
                    Caddy hosting    Webhook / Bark / ntfy
                         │
                    Calendar clients
~~~

Fetching, parsing, caching, and change detection are bounded by each source. Canonical merging therefore only uses successful input and avoids deleting known challenges because of a transient upstream failure.

## Configuration and Security

The configuration directory is resolved in this order: <code>$CHALLENGE_RADAR_CONFIG_DIR</code> → <code>/opt/apple-watch-challenge-radar/config</code> → <code>&lt;repository root&gt;/config</code>.

| File | Purpose |
| :--- | :--- |
| <code>config/config.yaml</code> | Source, path, feed, and notification settings |
| <code>config/challenge-names.yaml</code> | Longest-prefix mappings from challenge identifiers to Chinese names |
| <code>config/challenge-aliases.yaml</code> | Legacy-to-canonical identifier mappings |
| <code>config/workout-types.yaml</code> | Workout type number to Chinese name mappings |

Webhook URLs, Bark device keys, and ntfy topics must be injected through environment variables. Do not commit them to the repository or include them in generated calendars.

## Quality Checks

~~~bash
python -m pytest
python -m compileall -q src tests
~~~

GitHub Actions runs the test suite for pushes and pull requests targeting <code>main</code>. Local databases, ICS output, Python caches, virtual environments, and editor files are excluded by <code>.gitignore</code>.

## Project Layout

~~~text
.github/workflows/         GitHub Actions continuous integration
config/                    Version-controlled public YAML configuration
docs/
├── DEPLOYMENT.md          English deployment and operations guide
└── DEPLOYMENT_ZH.md       简体中文部署与运维指南
scripts/                   Installation and uninstallation scripts
src/challenge_radar/       Source adapters, parsing, merging, storage, ICS, notifications
tests/
├── fixtures/              Reproducible challenge-definition samples
├── unit/                  Module-level tests
└── integration/           Pipeline tests
environment.yml            Conda environment definition
pyproject.toml             Package metadata and development dependencies
~~~

## Documentation

| Document | Contents |
| :--- | :--- |
| [DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Debian/Ubuntu installation, systemd, Caddy, operations, upgrades, and troubleshooting |
| [DEPLOYMENT_ZH.md](./docs/DEPLOYMENT_ZH.md) | 简体中文部署、运维、升级与故障排查指南 |

## License

This project is licensed under the [GNU Affero General Public License v3.0](./LICENSE). If you run a modified version as a network service, you must make the corresponding source code available to its users under AGPL-3.0.
