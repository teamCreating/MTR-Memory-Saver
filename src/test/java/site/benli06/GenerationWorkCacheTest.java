package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(20)
class GenerationWorkCacheTest {
    private final AtomicInteger tickets = new AtomicInteger();
    private final ReadAdmission admission = new ReadAdmission(2, 100_000);
    private GenerationWorkCache<String, String, String> cache(int workers, int queue, Duration timeout) {
        return new GenerationWorkCache<>(workers, queue, timeout, admission, tickets::incrementAndGet, tickets::decrementAndGet);
    }
    private GenerationWorkCache.Prepared<String, String> text(String value) { return new GenerationWorkCache.Prepared<>(value, () -> value); }
    @Test void pathHitSkipsPreparationAndContentAliasesParseOnce() throws Exception {
        var reads = new AtomicInteger(); var parses = new AtomicInteger();
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            var first = cache.get("path", () -> { reads.incrementAndGet(); return new GenerationWorkCache.Prepared<>("same", () -> { parses.incrementAndGet(); return "mesh"; }); });
            assertEquals("mesh", first.get());
            assertSame(first, cache.get("path", () -> fail("Path hit performed read/digest")));
            assertEquals("mesh", cache.get("alias", () -> { reads.incrementAndGet(); return new GenerationWorkCache.Prepared<>("same", () -> { parses.incrementAndGet(); return "duplicate"; }); }).get());
            assertEquals(2, reads.get()); assertEquals(1, parses.get());
            cache.finishRegistration(); assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
            clean(cache);
        }
    }
    @Test void providerIdentityAndTextureArePartOfFastKey() {
        Object first = new String("provider"), second = new String("provider");
        assertEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(first, "a", "b", false));
        assertNotEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(second, "a", "b", false));
        assertNotEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(first, "a", "c", false));
        assertNotEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(first, "a", "b", true));
    }
    @Test void readAndParseFailureAllowRetryAndCleanTickets() throws Exception {
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            assertThrows(ExecutionException.class, () -> cache.get("path", () -> { throw new IllegalArgumentException("read"); }).get());
            assertThrows(ExecutionException.class, () -> cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> { throw new IllegalStateException("native parse ended without publication"); })).get());
            assertEquals("recovered", cache.get("path", () -> text("recovered")).get());
            assertEquals(2, cache.statistics().failures()); clean(cache);
        }
    }
    @Test void queueBackpressureDoesNotReadQueuedInputs() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var reads = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5)); var callers = Executors.newSingleThreadExecutor()) {
            var first = cache.get("a", () -> { reads.incrementAndGet(); entered.countDown(); await(release); return text("a"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var second = cache.get("b", () -> { reads.incrementAndGet(); return text("b"); });
            var third = callers.submit(() -> cache.get("c", () -> { reads.incrementAndGet(); return text("c"); }));
            assertThrows(TimeoutException.class, () -> third.get(80, TimeUnit.MILLISECONDS));
            assertEquals(1, reads.get()); assertEquals(2, cache.statistics().outstanding());
            release.countDown(); assertEquals("a", first.get()); assertEquals("b", second.get()); assertEquals("c", third.get().get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void reloadCancelsQueuedAndRunningWorkAndCannotPublishIntoNewEpoch() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var queuedReads = new AtomicInteger();
        try (var cache = cache(1, 2, Duration.ofSeconds(5))) {
            var old = cache.get("path", () -> {
                entered.countDown(); awaitIgnoringInterrupt(release); return text("old");
            });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var queued = cache.get("queued", () -> { queuedReads.incrementAndGet(); return text("queued"); });
            cache.beginReload(); assertTrue(old.isCancelled()); assertTrue(queued.isCancelled());
            assertEquals(1, tickets.get()); assertEquals(1, admission.active()); // Running memory still owns its permit.
            assertEquals(0, cache.statistics().pending());
            var fresh = cache.get("path", () -> text("new"));
            release.countDown(); assertEquals("new", fresh.get()); assertEquals(0, queuedReads.get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void timeoutIsTerminalButCannotReleaseStillRunningNativeMemory() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(1, 1, Duration.ofMillis(250))) {
            var hanging = cache.get("timeout", () -> { entered.countDown(); awaitIgnoringInterrupt(release); return text("late"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertInstanceOf(TimeoutException.class, assertThrows(ExecutionException.class, hanging::get).getCause());
            assertEquals(0, cache.statistics().pending()); assertEquals(1, tickets.get()); assertEquals(1, admission.active());
            release.countDown(); clean(cache);
            assertEquals("retry", cache.get("timeout", () -> text("retry")).get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void cancellationAndLateRegistrationCompletionReleaseEverything() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var running = cache.get("one", () -> { entered.countDown(); await(release); return text("one"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertTrue(running.cancel(true)); clean(cache);
            var later = cache.get("later", () -> text("later"));
            cache.finishRegistration(); assertEquals("later", later.get()); clean(cache);
            assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
        } finally { release.countDown(); }
    }
    @Test void oneThousandEpochsMixingSuccessFailureAndRetirementDoNotAccumulate() throws Exception {
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            for (int i = 0; i < 1000; i++) {
                assertEquals("mesh", cache.get("path", () -> text("mesh")).get());
                assertThrows(ExecutionException.class, () -> cache.get("bad", () -> { throw new IllegalStateException("fixture"); }).get());
                cache.finishRegistration(); cache.beginReload();
                assertEquals(0, cache.statistics().pending()); assertEquals(0, cache.statistics().paths());
            }
            clean(cache);
        }
    }
    @Test void admissionHookFailureReturnsSlot() throws Exception {
        var calls = new AtomicInteger();
        try (var cache = new GenerationWorkCache<String, String, String>(1, 1, Duration.ofSeconds(5), admission,
                () -> { if (calls.getAndIncrement() == 0) throw new IllegalStateException("construction hook"); tickets.incrementAndGet(); }, tickets::decrementAndGet)) {
            assertThrows(IllegalStateException.class, () -> cache.get("bad", () -> text("bad")));
            assertEquals("good", cache.get("good", () -> text("good")).get()); clean(cache);
        }
    }
    private void clean(GenerationWorkCache<?, ?, ?> cache) throws Exception {
        eventually(() -> cache.statistics().outstanding() == 0 && tickets.get() == 0 && admission.active() == 0);
        assertEquals(0, cache.statistics().pending()); assertEquals(0, cache.statistics().queued());
    }
    private static void eventually(BooleanSupplier predicate) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!predicate.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(2);
        assertTrue(predicate.getAsBoolean(), "Cleanup did not complete");
    }
    private static void await(CountDownLatch latch) {
        try { if (!latch.await(5, TimeUnit.SECONDS)) throw new AssertionError("fixture timed out"); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new CancellationException(); }
    }
    private static void awaitIgnoringInterrupt(CountDownLatch latch) {
        while (true) { try { if (!latch.await(5, TimeUnit.SECONDS)) throw new AssertionError("fixture timed out"); return; } catch (InterruptedException ignored) {} }
    }
}
