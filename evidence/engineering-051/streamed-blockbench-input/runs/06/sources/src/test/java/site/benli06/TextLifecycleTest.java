package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Random;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(20)
class TextLifecycleTest {
    @Test void exactCodeUnitsAndFirstReaderIdentity() {
        var admission = new ReadAdmission(2, 100_000);
        var cache = new BoundedTextCache(1_000_000, admission);
        String[] values = {"", "ascii", "\u0000\ud800\udc00\udfff", "a".repeat(4095) + "\ud800\udc00" + "\u03b1".repeat(10_000)};
        for (int i = 0; i < values.length; i++) {
            String value = values[i], key = "key" + i;
            assertSame(value, cache.get(key, ignored -> value));
            assertEquals(value, cache.get(key, ignored -> fail("Hit reread the input")));
        }
        assertTrue(cache.statistics()[1] > 0);
        assertEquals(0, admission.active());
    }
    @Test void oversizedInputsBypassCompressionAndNeverExceedLruWeight() {
        var cache = new BoundedTextCache(1024, new ReadAdmission(2, 100_000));
        String oversized = "a".repeat(4096);
        assertSame(oversized, cache.get("oversized", ignored -> oversized));
        assertEquals(0, cache.activity()[3]);
        assertEquals(1, cache.activity()[4]);
        for (int i = 0; i < 100; i++) cache.get("entry" + i, ignored -> "abcd".repeat(90));
        assertTrue(cache.budgetStatistics()[2] <= 1024);
        assertTrue(cache.budgetStatistics()[3] > 0);
    }
    @Test void incompressibleUtf16RemainsExact() {
        var random = new Random(5041);
        char[] chars = new char[12_000];
        for (int i = 0; i < chars.length; i++) chars[i] = (char) random.nextInt(65536);
        String value = new String(chars);
        var cache = new BoundedTextCache(100_000, new ReadAdmission(1, 100_000));
        assertSame(value, cache.get("random", ignored -> value));
        assertEquals(value, cache.get("random", ignored -> fail()));
        assertEquals(0, cache.statistics()[1]);
    }
    @Test void concurrentSingleFlightAndFailureRetry() throws Exception {
        var cache = new BoundedTextCache(100_000, new ReadAdmission(2, 100_000));
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var reads = new AtomicInteger();
        try (var pool = Executors.newFixedThreadPool(8)) {
            var first = pool.submit(() -> cache.get("one", ignored -> {
                reads.incrementAndGet(); entered.countDown(); await(release); return "text";
            }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var followers = new java.util.ArrayList<Future<String>>();
            for (int i = 0; i < 7; i++) followers.add(pool.submit(() -> cache.get("one", ignored -> { reads.incrementAndGet(); return "text"; })));
            release.countDown(); assertEquals("text", first.get());
            for (var follower : followers) assertEquals("text", follower.get());
            assertEquals(1, reads.get());
        }
        assertThrows(IllegalArgumentException.class, () -> cache.get("bad", ignored -> { throw new IllegalArgumentException("read failed"); }));
        assertEquals(0, cache.activity()[6]);
        assertEquals("recovered", cache.get("bad", ignored -> "recovered"));
        assertNull(cache.get("null", ignored -> null));
        assertNull(cache.get("null", ignored -> null));
    }
    @Test void reloadDuringReaderCannotPublishOldText() throws Exception {
        var admission = new ReadAdmission(2, 1000);
        var cache = new BoundedTextCache(10000, admission);
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            var old = pool.submit(() -> cache.get("model", ignored -> { entered.countDown(); await(release); return "old"; }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            cache.clear();
            assertEquals("new", cache.get("model", ignored -> "new"));
            release.countDown();
            assertInstanceOf(CancellationException.class, assertThrows(ExecutionException.class, old::get).getCause());
            assertEquals("new", cache.get("model", ignored -> fail()));
        } finally { release.countDown(); }
        assertEquals(0, admission.active());
    }
    @Test void segmentedGuardAndIoFailureReleaseAdmissionWithoutClosingNativeStream() throws Exception {
        var admission = new ReadAdmission(1, 10);
        var closed = new java.util.concurrent.atomic.AtomicBoolean();
        var stream = new ByteArrayInputStream("too long for limit".getBytes(StandardCharsets.UTF_8)) {
            @Override public void close() { closed.set(true); }
        };
        assertThrows(IllegalStateException.class, () -> SegmentedResourceText.read(stream, StandardCharsets.UTF_8, admission));
        assertEquals(0, admission.active()); assertFalse(closed.get());
        var broken = new java.io.InputStream() {
            @Override public int read() throws IOException { throw new IOException("fixture"); }
            @Override public void close() { closed.set(true); }
        };
        assertThrows(IOException.class, () -> SegmentedResourceText.read(broken, StandardCharsets.UTF_8, admission));
        assertEquals(0, admission.active()); assertFalse(closed.get());
        assertEquals("okay", SegmentedResourceText.read(new ByteArrayInputStream("okay".getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission));
    }
    @Test void nestedAdmissionAndInterruptedWaitDoNotLeak() throws Exception {
        var admission = new ReadAdmission(1, 100);
        try (var outer = admission.open(); var nested = admission.open()) {
            assertEquals(1, admission.active());
            var result = new CompletableFuture<Boolean>();
            Thread waiting = new Thread(() -> {
                Thread.currentThread().interrupt();
                assertThrows(CancellationException.class, admission::open);
                result.complete(Thread.currentThread().isInterrupted());
            });
            waiting.start(); assertTrue(result.get(5, TimeUnit.SECONDS)); waiting.join();
            nested.close(); nested.close();
            assertEquals(1, admission.active());
        }
        assertEquals(0, admission.active());
    }
    @Test void repeatedTextGenerationsReturnToZero() {
        var admission = new ReadAdmission(2, 1000);
        var cache = new BoundedTextCache(5000, admission);
        for (int i = 0; i < 1000; i++) {
            assertEquals("data", cache.get("path", ignored -> "data"));
            cache.clear();
            assertEquals(0, cache.statistics()[0]); assertEquals(0, cache.activity()[6]);
            assertEquals(0, admission.active());
        }
    }
    @Test void reloadRejectsTextCallerStillWaitingForReadAdmission() throws Exception {
        var admission = new ReadAdmission(1, 1000); var cache = new BoundedTextCache(10000, admission);
        var result = new CompletableFuture<String>(); var reads = new AtomicInteger();
        Thread caller = new Thread(() -> {
            try { result.complete(cache.get("crossing", ignored -> { reads.incrementAndGet(); return "stale"; })); }
            catch (Throwable error) { result.completeExceptionally(error); }
        });
        try (var scope = admission.open()) {
            caller.start(); ThreadTestSupport.awaiting(caller, "open"); cache.clear();
            assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS));
            assertEquals(1, admission.active());
        }
        assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS)); caller.join();
        assertEquals(0, reads.get()); assertEquals(0, cache.statistics()[0]); assertEquals(0, admission.active());
        assertEquals("fresh", cache.get("crossing", ignored -> "fresh"));
    }
    @Test void interruptedSingleFlightFollowerDoesNotCancelOwner() throws Exception {
        var admission = new ReadAdmission(2, 1000); var cache = new BoundedTextCache(10000, admission);
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            var owner = pool.submit(() -> cache.get("shared", ignored -> { entered.countDown(); await(release); return "text"; }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var result = new CompletableFuture<Boolean>();
            Thread follower = new Thread(() -> {
                try {
                    assertThrows(CancellationException.class, () -> cache.get("shared", ignored -> fail("Follower reread")));
                    result.complete(Thread.currentThread().isInterrupted());
                } catch (Throwable error) { result.completeExceptionally(error); }
            });
            follower.start(); ThreadTestSupport.awaiting(follower, "await"); follower.interrupt();
            assertTrue(result.get(5, TimeUnit.SECONDS)); follower.join();
            assertFalse(owner.isDone()); release.countDown(); assertEquals("text", owner.get());
            assertEquals("text", cache.get("shared", ignored -> fail()));
        } finally { release.countDown(); }
        assertEquals(0, admission.active()); assertEquals(0, cache.activity()[6]);
    }
    @Test void reloadCancelsSingleFlightFollowerAndPreservesReplacement() throws Exception {
        var admission = new ReadAdmission(2, 1000); var cache = new BoundedTextCache(10000, admission);
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var pool = Executors.newSingleThreadExecutor()) {
            var owner = pool.submit(() -> cache.get("shared", ignored -> { entered.countDown(); await(release); return "old"; }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var result = new CompletableFuture<String>();
            Thread follower = new Thread(() -> {
                try { result.complete(cache.get("shared", ignored -> fail("Follower reread"))); }
                catch (Throwable error) { result.completeExceptionally(error); }
            });
            follower.start(); ThreadTestSupport.awaiting(follower, "await"); cache.clear();
            assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS)); follower.join();
            assertEquals("new", cache.get("shared", ignored -> "new")); release.countDown();
            assertInstanceOf(CancellationException.class, assertThrows(ExecutionException.class, owner::get).getCause());
            assertEquals("new", cache.get("shared", ignored -> fail()));
        } finally { release.countDown(); }
        assertEquals(0, admission.active()); assertEquals(0, cache.activity()[6]);
    }
    private static void await(CountDownLatch latch) {
        try { if (!latch.await(5, TimeUnit.SECONDS)) throw new AssertionError("Fixture timed out"); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new CancellationException(); }
    }
}
