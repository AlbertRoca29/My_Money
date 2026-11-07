# My Money Wallet (Android)

A tiny Android app (about 20 KB, no libraries) that sends every **Google Wallet** payment to your
My Money server, where it waits in Gastos under "card payments to review". Tap one to add it, already
filled in: name, amount, date, and the category you used last time for that place.

```
Google Wallet notification ──▶ this app ──HTTPS──▶ your Cloud Run /api/wallet/notify ──▶ Gastos inbox
"BALUARD VALENCIA"                (reads only Wallet's,   (token checked, duplicates          (you pick the
"€6.03 with Trade Republic…"      queues if offline)       skipped: gastos/wallet.py)          category, Add)
```

Nothing goes anywhere else: no Google account, analytics, Play Store or third-party service.

## Build

```bash
android/build.sh          # -> android/build/my-money-wallet.apk
```

It uses the Android SDK's own tools directly (no Gradle). Needs, once:
- the SDK in `~/Android/Sdk` with `platforms;android-35` and `build-tools;35.0.0`
  (`~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk "platforms;android-35" "build-tools;35.0.0"`)
- a JDK: `javac` on PATH, `JAVA_HOME`, or one unpacked in `~/.local/jdk/`

The signing key is made on the first build in `~/.android/my-money-wallet.jks`. **Keep it**: a new build
only installs over the old app if it is signed with the same key. Bump `versionCode` in
AndroidManifest.xml for each new build.

## Set up

1. Server: `./deploy.sh wallet-token` (makes the token in Secret Manager and prints it with the URL),
   then `./deploy.sh` so Cloud Run gets it.
2. Copy the APK to the phone and open it (allow "install unknown apps" for your file manager once).
3. In the app: paste the URL and token → **Save and send a test** → "Sent ✓".
4. **Allow notification access**, then **Don't optimise battery**, so Android doesn't stop it.
5. Google Wallet: Settings → Notifications → keep payment notifications on (silent is fine).

## Notes

- Only phone payments: paying with the plastic card shows no Wallet notification.
- Parsing is on the server (`gastos/wallet.py`), so if Wallet changes its wording only the server changes.
- Refunds ("-€3.00") and non-payment Wallet notifications are ignored.
