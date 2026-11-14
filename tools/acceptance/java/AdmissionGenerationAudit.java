package site.benli06.audit;

import site.benli06.*;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Independent negative control compiled against either historical or current core sources. */
public final class AdmissionGenerationAudit {
    private static void hold(CountDownLatch release) {
        for (;;) try {
            if (!release.await(10, TimeUnit.SECONDS)) throw new AssertionError("Fixture timed out");
            return;
        } catch (InterruptedException ignored) { /* Preserve a real running owner after retirement. */ }
    }
    private static void waiting(Thread thread, String method) throws Exception {
        long started = System.nanoTime();
        while (System.nanoTime() - started < TimeUnit.SECONDS.toNanos(5)) {
            boolean inside = Arrays.stream(thread.getStackTrace()).anyMatch(frame -> frame.getMethodName().equals(method));
            if (inside && (thread.getState() == Thread.State.WAITING || thread.getState() == Thread.State.TIMED_WAITING)) return;
            Thread.sleep(2);
        }
        throw new AssertionError("Caller did not reach " + method);
    }
    private static GenerationWorkCache.Prepared<String, String> text(String value) {
        return new GenerationWorkCache.Prepared<>(value, () -> value);
    }
    public static void main(String[] args) throws Exception {
        var tickets = new AtomicInteger(); var reads = new AtomicInteger();
        var admission = new ReadAdmission(2, 100000);
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        boolean modelRejected;
        try (var cache = new GenerationWorkCache<String, String, String>(1, 1, Duration.ofSeconds(10), admission,
                tickets::incrementAndGet, tickets::decrementAndGet)) {
            cache.get("running", () -> { entered.countDown(); hold(release); return text("old"); });
            if (!entered.await(5, TimeUnit.SECONDS)) throw new AssertionError("No owner");
            cache.get("queued", () -> text("queued"));
            var result = new CompletableFuture<CompletableFuture<String>>();
            Thread caller = new Thread(() -> {
                try { result.complete(cache.get("crossing", () -> { reads.incrementAndGet(); return text("stale"); })); }
                catch (Throwable error) { result.completeExceptionally(error); }
            });
            caller.start(); waiting(caller, "acquireSlot"); cache.beginReload();
            CompletableFuture<String> crossed = null;
            try { crossed = result.get(5, TimeUnit.SECONDS); modelRejected = false; }
            catch (CancellationException expected) { modelRejected = true; }
            release.countDown(); caller.join();
            if (crossed != null && !crossed.get(5, TimeUnit.SECONDS).equals("stale")) throw new AssertionError("Wrong negative-control result");
            long started = System.nanoTime();
            while (cache.statistics().outstanding() != 0 && System.nanoTime() - started < TimeUnit.SECONDS.toNanos(5)) Thread.sleep(2);
            if (cache.statistics().outstanding() != 0 || cache.statistics().pending() != 0 || tickets.get() != 0 || admission.active() != 0)
                throw new AssertionError("Model work did not settle");
            if (!cache.get("fresh", () -> text("fresh")).get(5, TimeUnit.SECONDS).equals("fresh")) throw new AssertionError("Retry failed");
        } finally { release.countDown(); }
        var textAdmission = new ReadAdmission(1, 100000); var cache = new BoundedTextCache(100000, textAdmission);
        var textReads = new AtomicInteger(); var result = new CompletableFuture<String>();
        Thread caller = new Thread(() -> {
            try { result.complete(cache.get("crossing", ignored -> { textReads.incrementAndGet(); return "stale"; })); }
            catch (Throwable error) { result.completeExceptionally(error); }
        });
        boolean textRejected;
        try (var scope = textAdmission.open()) {
            caller.start(); waiting(caller, "open"); cache.clear();
            try { result.get(500, TimeUnit.MILLISECONDS); throw new AssertionError("Read bypassed held permit"); }
            catch (CancellationException expected) { textRejected = true; }
            catch (TimeoutException expected) { textRejected = false; }
            if (textAdmission.active() != 1) throw new AssertionError("Running owner lost permit");
        }
        if (!textRejected && !result.get(5, TimeUnit.SECONDS).equals("stale")) throw new AssertionError("Wrong text negative control");
        caller.join();
        if (textAdmission.active() != 0) throw new AssertionError("Text permit leaked");
        System.out.printf("{\"model_waiter_rejected\":%s,\"model_stale_reads\":%d,\"text_waiter_rejected_before_owner_exit\":%s,\"text_stale_reads\":%d,\"cleanup_verified\":true}%n",
                modelRejected, reads.get(), textRejected, textReads.get());
    }
}
