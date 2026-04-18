# Broken Lunch GR — Android

Jetpack Compose + Hilt + Retrofit + Google Maps Compose. Kotlin 2.0, AGP 8.7, min SDK 26, target/compile SDK 36.

## First-time setup

1. `cp local.properties.example local.properties` and fill in `MAPS_API_KEY` and `BACKEND_URL`.
2. Open `android/` in Android Studio (Hedgehog 2023.1+ recommended; Koala or newer for Kotlin 2.0).
3. Let Gradle sync. Wrapper pulls Gradle 8.10.2 on first run.

## Run

- Emulator: `BACKEND_URL=http://10.0.2.2:8000/` (points to the host machine's localhost).
- Physical device on same Wi-Fi: `BACKEND_URL=http://<pc-lan-ip>:8000/`.

`./gradlew :app:installDebug` or use Android Studio's run button.

## Module layout

```
app/src/main/java/com/brokenlunch/gr/
├── BrokenLunchApp.kt   # @HiltAndroidApp
├── MainActivity.kt     # @AndroidEntryPoint, hosts Compose
└── ui/theme/           # tier + verification color tokens
```

More packages (`data/`, `di/`, `ui/map/`, etc.) are added by Tasks 2.2 and 2.3.
