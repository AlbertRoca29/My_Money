package com.mymoney.wallet;

import android.app.Notification;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

/** Android hands every notification to this service; only Google Wallet's go further. */
public class WalletListener extends NotificationListenerService {
    static final String WALLET = "com.google.android.apps.walletnfcrel";

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        take(sbn);
    }

    /** On start (or after Android restarted the service): pick up Wallet payments still on screen.
     *  The server ignores ones it already has. */
    @Override
    public void onListenerConnected() {
        try {
            for (StatusBarNotification sbn : getActiveNotifications()) take(sbn);
        } catch (RuntimeException ignored) {
        }
    }

    private void take(StatusBarNotification sbn) {
        if (sbn == null || !WALLET.equals(sbn.getPackageName())) return;
        Bundle x = sbn.getNotification().extras;
        String title = str(x.getCharSequence(Notification.EXTRA_TITLE));
        String text = str(x.getCharSequence(Notification.EXTRA_BIG_TEXT));
        if (text.isEmpty()) text = str(x.getCharSequence(Notification.EXTRA_TEXT));
        // Only what looks like a payment ("€6.03 with …", "6,03 € con …"): Wallet also posts tips and card news
        if (title.isEmpty() || !text.matches("(?s).*(€|EUR|\\$|£)\\s*\\d.*|(?s).*\\d\\s*(€|EUR).*")) return;
        Outbox.add(this, sbn.getKey(), title, text, sbn.getPostTime());
        new Thread(() -> Outbox.flush(getApplicationContext())).start();
    }

    private static String str(CharSequence s) {
        return s == null ? "" : s.toString().trim();
    }
}
