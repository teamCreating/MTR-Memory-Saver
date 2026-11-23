package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.util.concurrent.CancellationException;
import org.junit.jupiter.api.Test;

class BoundaryLimitsTest {
    @Test void malformedNonpositiveAndOverflowPropertiesCannotSilentlyUseDefaults() {
        String key = "mtr.memory.test.limit", previous = System.getProperty(key);
        try {
            System.clearProperty(key); assertEquals(17, ReadAdmission.positiveProperty(key, 17));
            for (String invalid : new String[]{"", "text", "1.5", "0", "-1", "9223372036854775808"}) {
                System.setProperty(key, invalid);
                assertThrows(IllegalArgumentException.class, () -> ReadAdmission.positiveLongProperty(key, 17), invalid);
            }
            System.setProperty(key, "2147483648");
            assertThrows(IllegalArgumentException.class, () -> ReadAdmission.positiveProperty(key, 17));
            assertEquals(2147483648L, ReadAdmission.positiveLongProperty(key, 17));
            System.setProperty(key, "0x20"); assertEquals(32, ReadAdmission.positiveProperty(key, 17));
            System.setProperty(key, "1"); assertEquals(1, ReadAdmission.positiveProperty(key, 17));
        } finally { if (previous == null) System.clearProperty(key); else System.setProperty(key, previous); }
    }
    @Test void exactTextLimitSucceedsAndLimitPlusOneFails() {
        var admission = new ReadAdmission(1, 10); var cache = new BoundedTextCache(1000, admission);
        assertEquals("a".repeat(10), cache.get("exact", ignored -> "a".repeat(10)));
        assertThrows(IllegalStateException.class, () -> cache.get("large", ignored -> "a".repeat(11)));
        assertEquals("retry", cache.get("large", ignored -> "retry")); assertEquals(0, admission.active());
        assertThrows(IllegalArgumentException.class, () -> new ReadAdmission(0, 10));
        assertThrows(IllegalArgumentException.class, () -> new ReadAdmission(1, 0));
        assertThrows(IllegalArgumentException.class, () -> new ReadAdmission(1, Integer.MAX_VALUE));
        assertThrows(IllegalArgumentException.class, () -> new BoundedTextCache(0, admission));
    }
    @Test void invalidSchedulerLimitsFailBeforeCreatingWork() {
        var admission = new ReadAdmission(1, 100);
        assertThrows(IllegalArgumentException.class, () -> new GenerationWorkCache<>(0, 1, Duration.ofSeconds(1), admission, () -> {}, () -> {}));
        assertThrows(IllegalArgumentException.class, () -> new GenerationWorkCache<>(1, 0, Duration.ofSeconds(1), admission, () -> {}, () -> {}));
        assertThrows(IllegalArgumentException.class, () -> new GenerationWorkCache<>(1, 1, Duration.ZERO, admission, () -> {}, () -> {}));
        assertThrows(ArithmeticException.class, () -> new GenerationWorkCache<>(1, Integer.MAX_VALUE, Duration.ofSeconds(1), admission, () -> {}, () -> {}));
    }
    @Test void shortAndLongDigestsBothRespectInterruption() {
        Thread.currentThread().interrupt();
        try {
            assertThrows(CancellationException.class, () -> ResourceTextDigest.sha256("small"));
            assertThrows(CancellationException.class, () -> ResourceTextDigest.sha256("a".repeat(10000)));
        } finally { Thread.interrupted(); }
        assertDoesNotThrow(() -> ResourceTextDigest.sha256("small"));
    }
    @Test void cancellationPredicateFailureAfterPermitAcquisitionDoesNotLeak() {
        var admission = new ReadAdmission(1, 100); var calls = new java.util.concurrent.atomic.AtomicInteger();
        assertThrows(IllegalStateException.class, () -> admission.open(() -> {
            if (calls.incrementAndGet() == 2) throw new IllegalStateException("predicate failure");
            return false;
        }));
        assertEquals(0, admission.active());
        try (var scope = admission.open()) { assertEquals(1, admission.active()); }
        assertEquals(0, admission.active());
    }
}
