package com.mymoney.wallet;

import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Payments waiting to reach the server, kept on the phone (SharedPreferences) until it answers.
 * Nothing goes anywhere except the server URL you typed in the app: POST {url}/api/wallet/notify.
 */
final class Outbox {
    static final String PREFS = "wallet";
    private static final int JOB_ID = 1;
    private static final Object LOCK = new Object();

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static JSONArray queue(Context c) {
        try {
            return new JSONArray(prefs(c).getString("queue", "[]"));
        } catch (JSONException e) {
            return new JSONArray();
        }
    }

    /** Queue one notification, unless it was taken already: Wallet may post the same one again (an update,
     *  or Android restarting this app), and that must not become a second payment. */
    static void add(Context c, String key, String title, String text, long when) {
        synchronized (LOCK) {
            String id = key + "|" + title + "|" + text;
            JSONArray seen;
            try {
                seen = new JSONArray(prefs(c).getString("seen", "[]"));
            } catch (JSONException e) {
                seen = new JSONArray();
            }
            for (int i = 0; i < seen.length(); i++) if (id.equals(seen.optString(i))) return;
            seen.put(id);
            while (seen.length() > 100) seen.remove(0);
            prefs(c).edit().putString("seen", seen.toString()).apply();
            JSONArray q = queue(c);
            for (int i = 0; i < q.length(); i++) {
                JSONObject o = q.optJSONObject(i);
                if (o != null && title.equals(o.optString("title")) && text.equals(o.optString("text"))
                        && Math.abs(when - o.optLong("when")) < 60_000) return;
            }
            try {
                q.put(new JSONObject().put("title", title).put("text", text).put("when", when));
            } catch (JSONException ignored) {
            }
            prefs(c).edit().putString("queue", q.toString()).apply();
        }
    }

    /** Send everything queued. Returns null when all went, or what went wrong. Call off the main thread. */
    static String flush(Context c) {
        return flush(c, true);
    }

    /** retryLater false: called by FlushJob itself, which asks Android to retry instead. */
    static String flush(Context c, boolean retryLater) {
        SharedPreferences p = prefs(c);
        String base = p.getString("url", "").trim().replaceAll("/+$", "");
        String token = p.getString("token", "").trim();
        if (base.isEmpty() || token.isEmpty()) return "Set the server URL and token first";
        synchronized (LOCK) {
            JSONArray q = queue(c), left = new JSONArray();
            String problem = null;
            for (int i = 0; i < q.length(); i++) {
                JSONObject o = q.optJSONObject(i);
                if (o == null) continue;
                if (problem != null) { left.put(o); continue; }  // stop at the first failure, keep the rest
                try {
                    int code = post(base + "/api/wallet/notify", token, o.toString());
                    if (code == 401) problem = "The server refused the token";
                    else if (code >= 500 || code == 429) problem = "Server error " + code;
                    if (problem != null) left.put(o);
                    // other 4xx: a malformed item, dropping it is the only way forward
                } catch (IOException e) {
                    problem = "No connection: " + e.getMessage();
                    left.put(o);
                }
            }
            p.edit().putString("queue", left.toString())
                    .putString("last", problem == null ? "Sent ✓ " + now() : problem + " (" + now() + ")").apply();
            if (left.length() > 0 && retryLater && !isFinal(problem)) schedule(c);
            return problem;
        }
    }

    /** Problems that waiting won't fix: you have to change the URL or token. */
    static boolean isFinal(String problem) {
        return problem != null && (problem.startsWith("Set ") || problem.contains("token"));
    }

    /** Try again later, once there is a network: Android runs FlushJob, even if the app is closed. */
    static void schedule(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        js.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(c, FlushJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setBackoffCriteria(30_000, JobInfo.BACKOFF_POLICY_EXPONENTIAL)
                .setPersisted(true)  // survives a reboot (RECEIVE_BOOT_COMPLETED)
                .build());
    }

    private static int post(String url, String token, String json) throws IOException {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        try {
            con.setConnectTimeout(15_000);
            con.setReadTimeout(30_000);  // Cloud Run may be waking up
            con.setRequestMethod("POST");
            con.setDoOutput(true);
            con.setRequestProperty("Content-Type", "application/json");
            con.setRequestProperty("Authorization", "Bearer " + token);
            try (OutputStream out = con.getOutputStream()) {
                out.write(json.getBytes(StandardCharsets.UTF_8));
            }
            int code = con.getResponseCode();
            InputStream body = code < 400 ? con.getInputStream() : con.getErrorStream();
            if (body != null) body.close();
            return code;
        } finally {
            con.disconnect();
        }
    }

    private static String now() {
        return new java.text.SimpleDateFormat("d MMM HH:mm", java.util.Locale.getDefault()).format(new java.util.Date());
    }
}
