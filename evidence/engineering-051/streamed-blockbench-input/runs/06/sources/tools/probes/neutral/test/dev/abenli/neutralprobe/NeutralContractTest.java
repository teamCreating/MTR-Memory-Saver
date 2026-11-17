package dev.abenli.neutralprobe;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class NeutralContractTest {
    @TempDir Path temporary;

    @Test void unsupportedCompanionMeasurementsAreAbsent() throws Exception {
        var capabilities = ObservationSchema.resource("/capabilities.json").getAsJsonObject("capabilities");
        for (String key : new String[]{"module_counters", "active_read_permits", "text_workspace"})
            assertFalse(capabilities.get(key).getAsBoolean(), key);
        assertTrue(capabilities.get("frame_jfr").getAsBoolean());
        assertTrue(capabilities.get("native_epochs").getAsBoolean());
        var process = ObservationSchema.processIdentity();
        var value = ObservationSchema.envelope(Instant.parse("2026-11-15T00:00:00Z"), 123, process);
        ObservationSchema.counts(value, new RegistrationCounts(), 0);
        value.add("resource_epochs", ObservationSchema.epochs(new EpochTracker().state()));
        for (String key : new String[]{"shared_blockbench", "module_pending", "module_outstanding", "active_read_permits", "text_workspace"})
            assertFalse(value.has(key), key);
        assertEquals(process.get("start_instant"), value.get("process_created"));
        assertEquals("2026-11-15T00:00:00Z", value.get("observed_at").getAsString());
    }
    @Test void declarationsAndDistinctIdsRemainSeparate() {
        RegistrationCounts counts = new RegistrationCounts();
        counts.add("shared-id"); counts.add("shared-id"); counts.add("second-id");
        assertEquals(3, counts.declarations());
        assertEquals(2, counts.distinctIds());
        var value = ObservationSchema.envelope(Instant.now(), 0, ObservationSchema.processIdentity());
        ObservationSchema.counts(value, counts, 1);
        assertFalse(value.get("native_settled").getAsBoolean());
        assertEquals(1, value.get("native_pending").getAsInt());
    }
    @Test void snapshotCompletionTimestampCannotPrecedeItsSettledRead() {
        Instant started = Instant.parse("2026-11-15T00:00:00Z");
        var value = ObservationSchema.envelope(started, 100, ObservationSchema.processIdentity());
        ObservationSchema.counts(value, new RegistrationCounts(), 0);
        ObservationSchema.completedCapture(value, started.plusMillis(25), 25_000_100);
        assertEquals(started.toString(), value.get("capture_started_at").getAsString());
        assertEquals(100, value.get("capture_started_monotonic_nanos").getAsLong());
        assertEquals(started.plusMillis(25).toString(), value.get("observed_at").getAsString());
        assertEquals(value.get("observed_at"), value.get("timestamp"));
        assertEquals(25_000_100, value.get("monotonic_nanos").getAsLong());
        assertTrue(value.get("native_settled").getAsBoolean());
    }
    @Test void existingCacheObservationPreservesNativeKeysWithoutCreatingEntries() {
        Object nativeCache = new Object(), legacyCache = new Object();
        Map<Integer, Map<Integer, Object>> caches = new LinkedHashMap<>();
        caches.put(0, Map.of(0, nativeCache));
        caches.put(2, Map.of(4, legacyCache));
        var immutable = Map.copyOf(caches);
        var entries = ExistingCaches.entries(immutable);
        assertEquals(2, entries.size());
        assertTrue(entries.contains(new ExistingCaches.Entry<>(0, 0, nativeCache)));
        assertTrue(entries.contains(new ExistingCaches.Entry<>(2, 4, legacyCache)));
        assertEquals(2, immutable.size());
        assertEquals(0, ExistingCaches.entries(Map.<Integer, Map<Integer, Object>>of()).size());
    }
    @Test void exactRuntimeAndBinaryIdentityAreRequired() throws Exception {
        Path jar = temporary.resolve("mtr.jar");
        Files.writeString(jar, "same labelled binary");
        var target = new NativeTarget("official-nf248", "1.21.1", 21, "21.1.248", NativeTarget.sha256(jar));
        target.requireRuntime("1.21.1", 21, "21.1.248", jar);
        assertThrows(IllegalStateException.class, () -> target.requireRuntime("1.21.2", 21, "21.1.248", jar));
        assertThrows(IllegalStateException.class, () -> target.requireRuntime("1.21.1", 17, "21.1.248", jar));
        assertThrows(IllegalStateException.class, () -> target.requireRuntime("1.21.1", 21, "21.1.265", jar));
        Files.writeString(jar, "same label but replaced bytes");
        assertThrows(IllegalStateException.class, () -> target.requireRuntime("1.21.1", 21, "21.1.248", jar));
    }
    @Test void unsupportedTargetMetadataIsRejected() throws Exception {
        var identity = ObservationSchema.resource("/mtr-native-observer-target.json");
        assertEquals(21, NativeTarget.from(identity).java());
        identity.addProperty("variant", "unsupported");
        assertThrows(IllegalArgumentException.class, () -> NativeTarget.from(identity));
    }
}
