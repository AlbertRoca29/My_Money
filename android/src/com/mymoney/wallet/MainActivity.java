package com.mymoney.wallet;

import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** The only screen: where to send, the token, and whether Android lets the app read notifications. */
public class MainActivity extends Activity {
    private EditText url, token;
    private TextView access, battery, status;
    private Button accessBtn, batteryBtn;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        SharedPreferences p = Outbox.prefs(this);
        int pad = dp(20);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(pad, pad, pad, pad);

        TextView h = new TextView(this);
        h.setText("My Money Wallet");
        h.setTextSize(24);
        col.addView(h);
        col.addView(note("Sends each Google Wallet payment to your My Money server, to review in Gastos. "
                + "Nothing else is read or sent anywhere."));

        col.addView(label("Server URL"));
        url = field(p.getString("url", ""), "https://my-money-….run.app", InputType.TYPE_TEXT_VARIATION_URI);
        col.addView(url);
        col.addView(label("Token (./deploy.sh wallet-token)"));
        token = field(p.getString("token", ""), "64 characters",
                InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        col.addView(token);

        Button save = button("Save and send a test");
        save.setOnClickListener(v -> {
            p.edit().putString("url", url.getText().toString().trim())
                    .putString("token", token.getText().toString().trim()).apply();
            long now = System.currentTimeMillis();
            Outbox.add(this, "test" + now, "My Money Wallet test", "€0.01 with test card", now);
            status.setText("Sending…");
            sendNow();
        });
        col.addView(save);

        col.addView(label("Notification access"));
        access = note("");
        col.addView(access);
        accessBtn = button("Allow notification access");
        accessBtn.setOnClickListener(v ->
                startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        col.addView(accessBtn);

        col.addView(label("Battery"));
        battery = note("");
        col.addView(battery);
        batteryBtn = button("Don't optimise battery");
        batteryBtn.setOnClickListener(v -> startActivity(new Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName()))));
        col.addView(batteryBtn);

        col.addView(label("Status"));
        status = note("");
        col.addView(status);
        Button retry = button("Send queued now");
        retry.setOnClickListener(v -> { status.setText("Sending…"); sendNow(); });
        col.addView(retry);

        ScrollView sv = new ScrollView(this);
        sv.addView(col);
        sv.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(0, insets.getSystemWindowInsetTop(), 0, insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(sv);
    }

    @Override
    protected void onResume() {
        super.onResume();
        boolean ok = hasAccess();
        access.setText(ok ? "Allowed ✓" : "Not allowed yet: Wallet payments can't be read");
        accessBtn.setVisibility(ok ? View.GONE : View.VISIBLE);
        boolean free = getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(getPackageName());
        battery.setText(free ? "Not optimised ✓" : "Android may stop the app in the background");
        batteryBtn.setVisibility(free ? View.GONE : View.VISIBLE);
        showStatus();
    }

    private void sendNow() {
        Handler ui = new Handler(Looper.getMainLooper());
        new Thread(() -> {
            Outbox.flush(getApplicationContext());
            ui.post(this::showStatus);
        }).start();
    }

    private void showStatus() {
        int n = Outbox.queue(this).length();
        status.setText(Outbox.prefs(this).getString("last", "Nothing sent yet")
                + (n > 0 ? "\n" + n + " waiting to be sent" : ""));
    }

    private boolean hasAccess() {
        String flat = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
        return flat != null && flat.contains(new ComponentName(this, WalletListener.class).flattenToString());
    }

    private TextView label(String s) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(13);
        t.setAllCaps(true);
        t.setPadding(0, dp(22), 0, dp(4));
        t.setAlpha(0.6f);
        return t;
    }

    private TextView note(String s) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(15);
        t.setPadding(0, dp(4), 0, dp(4));
        return t;
    }

    private EditText field(String value, String hint, int variation) {
        EditText e = new EditText(this);
        e.setText(value);
        e.setHint(hint);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_TEXT | variation);
        return e;
    }

    private Button button(String s) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        b.setGravity(Gravity.CENTER);
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
