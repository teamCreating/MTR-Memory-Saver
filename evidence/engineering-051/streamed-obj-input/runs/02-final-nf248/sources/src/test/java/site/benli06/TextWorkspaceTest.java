package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

@Timeout(20)
class TextWorkspaceTest {
    @TempDir Path directory;

    @Test void defaultAllowsLargeInputsUsingAHeapQuarterWorkspace() {
        long heap = 3L * 1024 * 1024 * 1024;
        assertEquals(201326592, ReadAdmission.defaultMaxCodeUnits(heap));
        var admission = ReadAdmission.configured(heap);
        assertEquals(heap / 4, admission.workspaceStatistics()[0]);
        assertDoesNotThrow(() -> admission.checkLength(102035449));
        assertThrows(IllegalStateException.class, () -> admission.checkLength(admission.maxCodeUnits() + 1));
        assertEquals(Integer.MAX_VALUE - 8L, ReadAdmission.defaultMaxCodeUnits(Long.MAX_VALUE));
    }

    @Test void explicitLimitAndWorkspaceRemainStrict() {
        String limitKey = "mtr.memory.maxTextCodeUnits", budgetKey = "mtr.memory.textWorkspaceBytes";
        String oldLimit = System.getProperty(limitKey), oldBudget = System.getProperty(budgetKey);
        try {
            System.setProperty(limitKey, "10"); System.setProperty(budgetKey, "40");
            var admission = ReadAdmission.configured(4096);
            admission.checkLength(10);
            assertThrows(IllegalStateException.class, () -> admission.checkLength(11));
            System.setProperty(budgetKey, "39");
            assertThrows(IllegalArgumentException.class, () -> ReadAdmission.configured(4096));
            System.setProperty(limitKey, "9223372036854775807");
            assertThrows(IllegalArgumentException.class, () -> ReadAdmission.configured(4096));
        } finally {
            restore(limitKey, oldLimit); restore(budgetKey, oldBudget);
        }
    }

    @Test void snapshotsPreserveCharsetReplacementAndSupplementaryBoundaries() throws Exception {
        var admission = new ReadAdmission(2, 25000);
        for (String text : new String[]{"", "a".repeat(15000), "\u03b1".repeat(8191) + "🚆" + "\u0000\u4e2d".repeat(4000)}) {
            for (var charset : new java.nio.charset.Charset[]{StandardCharsets.UTF_8, StandardCharsets.UTF_16LE}) {
                byte[] bytes = text.getBytes(charset);
                assertEquals(text, SegmentedResourceText.read(new ByteArrayInputStream(bytes), charset, admission, directory));
                clean(admission);
            }
        }
        byte[] malformed = {(byte) 0xc0, (byte) 0xaf, (byte) 0xe2, (byte) 0x82};
        String expected = new String(malformed, StandardCharsets.UTF_8);
        assertEquals(expected, SegmentedResourceText.read(new ByteArrayInputStream(malformed), StandardCharsets.UTF_8, admission, directory));
        clean(admission);
    }

    @Test void snapshotsGuardExactDecodedUnitsAndDoNotCloseCallerStream() throws Exception {
        var admission = new ReadAdmission(2, 1000);
        var closed = new AtomicBoolean();
        InputStream stream = new ByteArrayInputStream("\u03b1".repeat(1000).getBytes(StandardCharsets.UTF_8)) {
            @Override public void close() { closed.set(true); }
        };
        assertEquals(1000, SegmentedResourceText.read(stream, StandardCharsets.UTF_8, admission, directory).length());
        assertFalse(closed.get()); clean(admission);
        assertThrows(IllegalStateException.class, () -> SegmentedResourceText.read(
                new ByteArrayInputStream("a".repeat(1001).getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission, directory));
        clean(admission);
    }

    @Test void failureAfterSpillingRemovesSnapshotAndReservations() throws Exception {
        var admission = new ReadAdmission(2, 20000);
        InputStream broken = new ByteArrayInputStream("a".repeat(15000).getBytes(StandardCharsets.UTF_8)) {
            private int reads;
            @Override public synchronized int read(byte[] bytes, int offset, int length) {
                if (++reads >= 3) throw new IllegalStateException("injected stream failure after spill");
                return super.read(bytes, offset, Math.min(length, 6000));
            }
        };
        assertThrows(IllegalStateException.class, () -> SegmentedResourceText.read(broken, StandardCharsets.UTF_8, admission, directory));
        clean(admission);
        Path file = Files.createFile(directory.resolve("cannot-be-a-directory"));
        assertThrows(IOException.class, () -> SegmentedResourceText.read(
                new ByteArrayInputStream("a".repeat(15000).getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission, file));
        Files.delete(file); clean(admission);
    }

    @Test void twoLargeUnknownReadersReleaseSharesBeforeWaitingForFullWorkspace() throws Exception {
        var admission = new ReadAdmission(2, 20000);
        var barrier = new CyclicBarrier(2);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var first = pool.submit(() -> readTogether(admission, barrier, "a".repeat(15000)));
            var second = pool.submit(() -> readTogether(admission, barrier, "\u03b1".repeat(16000)));
            assertEquals("a".repeat(15000), first.get(10, TimeUnit.SECONDS));
            assertEquals("\u03b1".repeat(16000), second.get(10, TimeUnit.SECONDS));
        }
        clean(admission);
        assertTrue(admission.workspaceStatistics()[2] <= admission.workspaceStatistics()[0]);
    }

    @Test void retirementWhileWaitingForWorkspaceCleansSnapshotAndReadPermit() throws Exception {
        var admission = new ReadAdmission(2, 20000);
        var retired = new AtomicBoolean();
        var result = new CompletableFuture<String>();
        Thread caller = new Thread(() -> {
            try (var scope = admission.open(retired::get)) {
                result.complete(SegmentedResourceText.read(new ByteArrayInputStream("a".repeat(15000).getBytes(StandardCharsets.UTF_8)),
                        StandardCharsets.UTF_8, admission, directory));
            } catch (Throwable error) { result.completeExceptionally(error); }
        });
        try (var held = admission.workspace().claim(admission.workspace().share())) {
            caller.start(); ThreadTestSupport.awaiting(caller, "claim");
            assertEquals(1, admission.active()); retired.set(true);
            assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS));
            caller.join();
        }
        clean(admission);
    }

    @Test void interruptedAtomicWaitAndForbiddenNestedClaimCannotLeak() throws Exception {
        var admission = new ReadAdmission(2, 1000);
        try (var held = admission.workspace().claim(3000)) {
            assertThrows(IllegalStateException.class, () -> admission.workspace().claim(1));
            var checked = new CompletableFuture<Boolean>();
            Thread caller = new Thread(() -> {
                try {
                    Thread.currentThread().interrupt();
                    assertThrows(CancellationException.class, () -> admission.workspace().claim(2000));
                    checked.complete(Thread.currentThread().isInterrupted());
                } catch (Throwable error) { checked.completeExceptionally(error); }
            });
            caller.start(); assertTrue(checked.get(5, TimeUnit.SECONDS)); caller.join();
            assertEquals(3000, admission.workspaceStatistics()[1]);
            assertEquals(0, admission.workspaceStatistics()[3]);
        }
        clean(admission);
    }

    @Test void compressionBypassesBusyWorkspaceAndRetainsExactRawCacheEntry() throws Exception {
        var admission = new ReadAdmission(2, 1000);
        var cache = new BoundedTextCache(5000, admission);
        String text = "a".repeat(100);
        try (var held = admission.workspace().claim(3800); var pool = Executors.newSingleThreadExecutor()) {
            assertSame(text, pool.submit(() -> cache.get("text", ignored -> text)).get(5, TimeUnit.SECONDS));
            assertEquals(0, cache.statistics()[1]);
            assertEquals(100, cache.statistics()[4]);
            assertSame(text, cache.get("text", ignored -> fail("Raw cache entry was discarded")));
        }
        clean(admission);
    }

    @Test void cacheRetirementCancelsUnpackWorkspaceWaitWithoutWaitingForItsOwner() throws Exception {
        var admission = new ReadAdmission(2, 10000);
        var cache = new BoundedTextCache(100000, admission);
        String text = "a".repeat(5000);
        cache.get("text", ignored -> text);
        assertEquals(1, cache.statistics()[1]);
        var result = new CompletableFuture<String>();
        Thread caller = new Thread(() -> {
            try { result.complete(cache.get("text", ignored -> fail("Unpack reread its source"))); }
            catch (Throwable error) { result.completeExceptionally(error); }
        });
        try (var held = admission.workspace().claim(39000)) {
            caller.start(); ThreadTestSupport.awaiting(caller, "claim"); cache.clear();
            assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS));
            caller.join(); assertEquals(39000, admission.workspaceStatistics()[1]);
        }
        clean(admission);
    }

    private String readTogether(ReadAdmission admission, CyclicBarrier barrier, String text) throws Exception {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        var input = new ByteArrayInputStream(bytes) {
            private boolean started;
            @Override public synchronized int read(byte[] target, int offset, int length) {
                if (!started) {
                    started = true;
                    try { barrier.await(5, TimeUnit.SECONDS); }
                    catch (Exception error) { throw new IllegalStateException(error); }
                }
                return super.read(target, offset, Math.min(length, 4000));
            }
        };
        return SegmentedResourceText.read(input, StandardCharsets.UTF_8, admission, directory);
    }
    private void clean(ReadAdmission admission) throws IOException {
        assertEquals(0, admission.active());
        assertEquals(0, admission.workspaceStatistics()[1]);
        assertEquals(0, admission.workspaceStatistics()[3]);
        try (var files = Files.list(directory)) { assertEquals(0, files.count()); }
    }
    private static void restore(String name, String previous) {
        if (previous == null) System.clearProperty(name); else System.setProperty(name, previous);
    }
}
