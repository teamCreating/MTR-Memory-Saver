package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.commons.io.IOUtils;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(10)
class StrictResourceTextTest {
    @Test void openFailureOccursInsideAdmissionAndReleasesIt() {
        var admission = new ReadAdmission(1, 100);
        var failure = new IOException("open failed");
        var error = assertThrows(UncheckedIOException.class, () -> StrictResourceText.read("test:open", () -> {
            assertEquals(1, admission.active());
            throw failure;
        }, admission));
        assertSame(failure, error.getCause());
        assertEquals(0, admission.active());
    }

    @Test void readFailureClosesStreamAndPreservesSuppressedCloseFailure() {
        var admission = new ReadAdmission(1, 100);
        var readFailure = new IOException("read failed");
        var closeFailure = new IOException("close failed");
        var closes = new AtomicInteger();
        var error = assertThrows(UncheckedIOException.class, () -> StrictResourceText.read("test:read", () -> new InputStream() {
            @Override public int read() throws IOException { throw readFailure; }
            @Override public void close() throws IOException { closes.incrementAndGet(); throw closeFailure; }
        }, admission));
        assertSame(readFailure, error.getCause());
        assertArrayEquals(new Throwable[]{closeFailure}, readFailure.getSuppressed());
        assertEquals(1, closes.get());
        assertEquals(0, admission.active());
    }

    @Test void closeFailureAfterDecodedTextRemainsAFailure() {
        var admission = new ReadAdmission(1, 100);
        var failure = new IOException("close failed");
        var error = assertThrows(UncheckedIOException.class, () -> StrictResourceText.read("test:close", () -> new ByteArrayInputStream(new byte[]{'o', 'k'}) {
            @Override public void close() throws IOException { throw failure; }
        }, admission));
        assertSame(failure, error.getCause());
        assertEquals(0, admission.active());
    }

    @Test void legalEmptyTextClosesOnceAndCanBeCached() {
        var admission = new ReadAdmission(1, 100);
        var cache = new BoundedTextCache(1024, admission);
        var closes = new AtomicInteger();
        assertEquals("", cache.get("test:empty", key -> StrictResourceText.read(key, () -> new ByteArrayInputStream(new byte[0]) {
            @Override public void close() { closes.incrementAndGet(); }
        }, admission)));
        assertEquals("", cache.get("test:empty", ignored -> fail("A successful empty resource should be cached")));
        assertEquals(1, closes.get());
        assertEquals(1, cache.statistics()[0]);
        assertEquals(0, admission.active());
    }

    @Test void utf8ReplacementAndSegmentBoundariesMatchNativeIoUtils() throws Exception {
        var admission = new ReadAdmission(1, 100_000);
        byte[][] inputs = {
                "a".repeat(8191).concat("\ud83d\ude86\u03b1").getBytes(StandardCharsets.UTF_8),
                {(byte) 0xC3, 0x28, (byte) 0xF0, 0x28, (byte) 0x8C, 0x28, (byte) 0xFF},
                {'a', (byte) 0xE2, (byte) 0x82}
        };
        for (byte[] bytes : inputs) {
            String expected = IOUtils.toString(new ByteArrayInputStream(bytes), StandardCharsets.UTF_8);
            assertEquals(expected, StrictResourceText.read("test:utf8", () -> new ByteArrayInputStream(bytes), admission));
        }
        assertEquals(0, admission.active());
    }

    @Test void sizeFailurePropagatesWithoutLosingCloseSuppression() {
        var admission = new ReadAdmission(1, 2);
        var closeFailure = new IOException("close failed");
        var error = assertThrows(IllegalStateException.class, () -> StrictResourceText.read("test:guard", () -> new ByteArrayInputStream(new byte[]{'a', 'b', 'c'}) {
            @Override public void close() throws IOException { throw closeFailure; }
        }, admission));
        assertArrayEquals(new Throwable[]{closeFailure}, error.getSuppressed());
        assertEquals(0, admission.active());
    }

    @Test void failedReadCannotCacheAnEmptyFallbackAndSamePathCanRetry() {
        var admission = new ReadAdmission(1, 100);
        var cache = new BoundedTextCache(1024, admission);
        var reads = new AtomicInteger();
        assertThrows(UncheckedIOException.class, () -> cache.get("test:retry", key -> StrictResourceText.read(key, () -> {
            reads.incrementAndGet();
            throw new IOException("first attempt failed");
        }, admission)));
        assertEquals(0, cache.statistics()[0]);
        assertEquals(0, cache.activity()[6]);
        assertEquals("corrected", cache.get("test:retry", key -> StrictResourceText.read(key, () -> {
            reads.incrementAndGet();
            return new ByteArrayInputStream("corrected".getBytes(StandardCharsets.UTF_8));
        }, admission)));
        assertEquals("corrected", cache.get("test:retry", ignored -> fail("Retry result should be cached")));
        assertEquals(2, reads.get());
        assertEquals(0, admission.active());
    }

    @Test void interruptionDuringReadRetainsInterruptAndClosesStream() {
        var admission = new ReadAdmission(1, 100);
        var closes = new AtomicInteger();
        try {
            assertThrows(CancellationException.class, () -> StrictResourceText.read("test:interrupted", () -> new InputStream() {
                private boolean emitted;
                @Override public int read() {
                    if (emitted) return -1;
                    emitted = true;
                    Thread.currentThread().interrupt();
                    return 'x';
                }
                @Override public void close() { closes.incrementAndGet(); }
            }, admission));
            assertTrue(Thread.currentThread().isInterrupted());
            assertEquals(1, closes.get());
            assertEquals(0, admission.active());
        } finally { Thread.interrupted(); }
    }
}
