#!/usr/bin/env bash
# Builds My Money Wallet into android/build/my-money-wallet.apk with the Android SDK's own tools
# (javac -> d8 -> aapt2 -> zipalign -> apksigner). No Gradle, no libraries.
#
# Needs: a JDK (javac, keytool), and the SDK with "platforms;android-35" and "build-tools;35.0.0" (see README.md).
# The signing key is made once in ~/.android/my-money-wallet.jks, outside the repo: keep it, since an
# update only installs over the old app when it is signed with the same key.
set -euo pipefail
cd "$(dirname "$0")"
SDK=${ANDROID_HOME:-$HOME/Android/Sdk}
BT=$SDK/build-tools/35.0.0
JAR=$SDK/platforms/android-35/android.jar
KEY=$HOME/.android/my-money-wallet.jks
OUT=build
# A JDK: JAVA_HOME, else javac on PATH, else one unpacked in ~/.local/jdk
if [ -z "${JAVA_HOME:-}" ] && ! command -v javac >/dev/null; then
  JAVA_HOME=$(ls -d "$HOME"/.local/jdk/*/ 2>/dev/null | tail -1)
fi
[ -n "${JAVA_HOME:-}" ] && export JAVA_HOME && export PATH="$JAVA_HOME/bin:$PATH"

rm -rf "$OUT" && mkdir -p "$OUT/classes" "$OUT/dex"

echo "== resources"
"$BT/aapt2" compile --dir res -o "$OUT/res.zip"
"$BT/aapt2" link -I "$JAR" --manifest AndroidManifest.xml -o "$OUT/base.apk" "$OUT/res.zip" \
  --java "$OUT/gen" --auto-add-overlay

echo "== java"
javac --release 11 -nowarn -classpath "$JAR" -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java')
"$BT/d8" --release --min-api 26 --lib "$JAR" --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')
(cd "$OUT/dex" && zip -q ../base.apk classes.dex)

echo "== sign"
if [ ! -f "$KEY" ]; then
  mkdir -p "$(dirname "$KEY")"
  keytool -genkeypair -keystore "$KEY" -storepass mymoney -keypass mymoney -alias wallet \
    -keyalg RSA -keysize 3072 -validity 36500 -dname "CN=My Money Wallet" >/dev/null
fi
"$BT/zipalign" -f -p 4 "$OUT/base.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks "$KEY" --ks-pass pass:mymoney --ks-key-alias wallet \
  --out "$OUT/my-money-wallet.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify "$OUT/my-money-wallet.apk"
echo "Built $(pwd)/$OUT/my-money-wallet.apk"
