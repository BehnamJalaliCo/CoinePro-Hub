# CoinePro HQ — Android

The owner's phone app for the hub at `https://hq.coinepro.com`: the same D3 design as the web (Divan design
system, IRANYekanX, right-to-left), built natively with Kotlin and Jetpack Compose.

| | |
|---|---|
| Package | `com.coinepro.hq` (debug: `com.coinepro.hq.debug`) |
| SDK | min 28 (Android 9), target 36, compile 37 |
| Toolchain | AGP 9.4.1 (built-in Kotlin), Kotlin 2.4.20, Gradle 9.7.1 (wrapper, checksum pinned), JDK 21 |
| UI | Compose BOM 2026.09.00, Material 3 only for sheets, dialogs and pull-to-refresh |
| Network | OkHttp 5 + kotlinx.serialization (snake_case), SSE via okhttp-sse |
| Sign-in | Credential Manager passkeys; session token encrypted with an Android Keystore AES-GCM key |

Every library is free and open source and pinned to an exact version (`gradle/libs.versions.toml`).

## What is in it

- **Sign-in and enrolment** — discoverable passkey sign-in; the one-time link from `make owner-enroll` opens
  the app directly (App Link `https://hq.coinepro.com/enroll#token=…`) or can be pasted.
- **Shell** — top bar (live-stream state, notifications, tools), bottom bar with the advisor's orb in the middle.
- **Command center** — greeting, what happened while away, the four numbers, cartable, the live holding orbit,
  today's planner and the month's budgets.
- **Cartable** — decisions by risk; a decision page with payload views (hire, deploy, budget change), cost and
  risk, and the **seal ritual**: press and hold 600 ms, then the passkey step-up for A3, hire, dismissal and budget
  changes. Reject (with a reason code), return with a note, ask in chat, review with the advisor.
- **Outputs** with the owner's 1–10 rating, **messages** and the **advisor** with live replies
  (`/threads/{code}/live`, falls back to polling), **companies** (departments, org chart, work), **employee**,
  **work** (delegation chain, budget, events), **treasury** (totals, cumulative month chart, token types,
  companies by their fixed palette slot, models, budgets, top consumers, connections), **planner** (week from
  Saturday), **notifications** (five levels; learning questions answered with one touch), **control** (kill
  switches; release needs the passkey), **audit** (hash-chain verification) and **settings** (devices,
  passkeys, theme, Khalvat, this app's signing fingerprint).
- **Live** — one SSE connection to `/api/v1/stream` while the app is in the foreground; events refresh the
  screens that show the touched data (the same invalidation map as the web).

## Layout

```
app/src/main/java/com/coinepro/hq/
  core/net/        Api (contract v1.2), Models
  core/auth/       Auth (sign-in, enrolment, step-up), Passkeys, TokenVault
  core/data/       QueryCache (shared cached queries), HoldingStream (SSE)
  core/format/     Jalali dates, figures, Persian labels
  designsystem/    Theme, icons and marks, components, seal, avatar and orb, charts, Markdown subset
  designsystem/generated/   made by scripts/gen_assets.py from design/ — never edited by hand
  ui/              screens
app/src/debug/     the demo holding (fixtures shared with the web); not in release builds
app/src/test/      API contract, formatting and screenshot tests; screenshots/ = every screen, night and day
```

## Build

```bash
export ANDROID_HOME=/path/to/android-sdk     # or sdk.dir in local.properties
./gradlew testDebugUnitTest assembleDebug assembleRelease
./gradlew recordRoborazziDebug               # refresh app/src/test/screenshots after a design change
python3 scripts/gen_assets.py                # after design/ changes (CI runs it with --check)
node --experimental-strip-types scripts/dump_demo_fixtures.mjs   # after the web's mock fixtures change
```

CI (`.github/workflows/clients.yml`) runs the tests and publishes both APKs to the prerelease
**android-latest**: `coinepro-hq.apk` is the app, `coinepro-hq-debug.apk` the development build with
**«نمایش آزمایشی»** on the sign-in screen (the demo holding, no server, no passkey).

## Passkeys on Android: three steps, all the owner's

Credential Manager only lets an app use the hub's passkeys when the domain vouches for the app. That needs the
app's signing key, which is the owner's alone.

1. **Signing key** — on the owner's own machine, once:
   `keytool -genkeypair -v -keystore coinepro-hq.jks -alias hq -keyalg RSA -keysize 4096 -validity 10000`.
   Keep it outside git. For CI add four repository secrets: `HQ_SIGNING_KEYSTORE_B64` (the file, base64),
   `HQ_SIGNING_STORE_PASSWORD`, `HQ_SIGNING_KEY_ALIAS`, `HQ_SIGNING_KEY_PASSWORD`. Locally,
   `apps/android/keystore.properties` (git-ignored, mode 600) with `storeFile`, `storePassword`, `keyAlias`,
   `keyPassword`.
2. **Digital Asset Links** — the web serves `https://hq.coinepro.com/.well-known/assetlinks.json` from two
   variables of the web service: `HQ_ANDROID_PACKAGES` (default `com.coinepro.hq`) and
   `HQ_ANDROID_CERT_SHA256` (the fingerprint, `AA:BB:…`; several allowed, comma-separated).
3. **API allow-list** — the API accepts the app's WebAuthn origin from `HQ_ANDROID_ORIGINS`
   (`android:apk-key-hash:…`).

The app shows both values under **تنظیمات → این اپ** with copy buttons, computed from the key it was signed with.
Until then the app installs and runs, the demo works in the debug build, and sign-in reports that the app is not
yet linked to the domain.

Push notifications (FCM) are not in this version: they need a Firebase project, which is the owner's decision.
The in-app stream covers notifications while the app is open.
