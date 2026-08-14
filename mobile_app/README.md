# AEGIS Mobile

Android app that screenshots MT5, sends screenshots to the AEGIS backend
for signal analysis, and auto-executes BUY/SELL via Android's
Accessibility Service.

## Build status

**Source-complete and the Gradle wrapper is now real** (`gradlew`,
`gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` are genuine, verified
files - the jar contains real `org.gradle.cli.*` classes, `gradlew`
correctly references it via `CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar`).
`.github/workflows/mobile-ci.yml` builds via the standard `./gradlew`
path, with `gradle/actions/wrapper-validation` checking the jar's
checksum against Gradle's official list before every run.

**This project has still never actually been compiled.** A working
wrapper removes the "nothing to bootstrap Gradle with" blocker; it does
not mean the Kotlin code is guaranteed to compile cleanly on the first
try. Every file has been statically checked (imports resolve, XML/Kotlin
IDs match, braces/parens balance) but this environment has no Android
SDK, so nothing here has run through a real compiler yet. Expect normal
first-build friction - that's expected, not a sign something is more
broken than usual.

**If you're testing this:** trigger the GitHub Actions workflow (push to
`mobile_app/**` or run it manually) and send back the exact log output,
including which step it reached and the full error text if it fails. That
tells us something neither of us currently knows, and lets fixes target
the actual problem instead of a guess at one.

## Module map

| Path | What it does |
|---|---|
| `ui/MainActivity.kt` | Start/stop capture, health readout, battery exemption prompt |
| `ui/SettingsActivity.kt` | Server IP, API key, account ID configuration |
| `ui/StatusViewModel.kt` | Exposes latest signal to the UI |
| `capture/ScreenCaptureService.kt` | Foreground service: MediaProjection capture loop, heartbeat, notification |
| `capture/ScreenshotCacheManager.kt` | Disk-backed offline queue when the backend is unreachable |
| `automation/Mt5AccessibilityService.kt` | Finds and taps Buy/Sell in the MT5 app |
| `network/ApiService.kt` / `RetrofitClient.kt` | Backend API client |
| `data/` | Shared preferences (DataStore), in-process signal/health state |

## Setup

1. Open in Android Studio, let Gradle sync (needs internet - downloads AGP
   8.5.2 + dependencies), or run `./gradlew assembleDebug` from the
   command line / CI.
2. Install the resulting APK on a device with MT5 installed and logged in.
3. In AEGIS Settings, set:
   - **Brain Server URL** - full HTTPS base, e.g. `https://your-service.onrender.com`
     (not a bare LAN IP; Render terminates TLS on 443)
   - **API Key** - the admin bootstrap key from first deploy logs, or the
     per-account key shown once when a subscription activates (see
     `docs/SECURITY.md`). Wrong key → `401`; key for a different account → `403`
   - **Account ID** - optional; defaults to this device's Android ID if left blank
4. Grant screen-capture permission, enable the Accessibility Service, and
   tap "Allow background running" when prompted.
5. First upload after a Render free-tier sleep can take 30–90s (cold start).
   The app retries once and queues offline; subsequent captures are fast.

## What's genuinely unverified here

- The Buy/Sell tap logic in `Mt5AccessibilityService.kt` searches for
  clickable nodes containing "Buy"/"Sell" text. Real MT5 order placement
  needs volume entry and a confirm dialog - this is a starting point, not
  a complete flow. Inspect MT5's actual node tree with Google's
  "Accessibility Scanner" app and extend it.
- The offline screenshot cache (`ScreenshotCacheManager`) has never been
  tested against a real network outage - verify it drains in order and
  respects the file cap on a real device before relying on it.
