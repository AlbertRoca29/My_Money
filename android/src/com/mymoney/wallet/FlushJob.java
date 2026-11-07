package com.mymoney.wallet;

import android.app.job.JobParameters;
import android.app.job.JobService;

/** Run by Android once there is a network, when something is still queued (Outbox.schedule). */
public class FlushJob extends JobService {
    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            String problem = Outbox.flush(getApplicationContext(), false);
            jobFinished(params, problem != null && !Outbox.isFinal(problem));  // true: Android retries, backing off
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
