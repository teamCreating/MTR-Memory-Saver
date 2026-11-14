package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.mtr.libraries.com.google.gson.JsonObject;

@Timeout(20)
class VehicleJsonLifecycleTest {
    @Test void reloadRejectsJsonCallerWaitingForReadAdmission() throws Exception {
        VehicleJsonCache.beginReload();
        var admission = new ReadAdmission(1, 1000);
        var result = new CompletableFuture<JsonObject>();
        Thread caller = new Thread(() -> {
            try { result.complete(VehicleJsonCache.parse("{\"value\":\"old\"}", admission)); }
            catch (Throwable error) { result.completeExceptionally(error); }
        });
        try (var scope = admission.open()) {
            caller.start(); ThreadTestSupport.awaiting(caller, "open"); VehicleJsonCache.beginReload();
            assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS));
            assertEquals(1, admission.active());
        }
        assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS)); caller.join();
        assertEquals("new", VehicleJsonCache.parse("{\"value\":\"new\"}", admission).get("value").getAsString());
        assertEquals(0, admission.active()); VehicleJsonCache.finishRegistration();
    }
    @Test void concurrentIdenticalInputsShareTreeAndRetiredTreeIsNotReused() throws Exception {
        VehicleJsonCache.beginReload();
        String raw = "{\"parts\":[{\"names\":[\"shared\"]}],\"modelYOffset\":-0.0}";
        var admission = new ReadAdmission(3, 1000); var start = new CountDownLatch(1);
        JsonObject shared;
        try (var pool = Executors.newFixedThreadPool(8)) {
            var results = new java.util.ArrayList<Future<JsonObject>>();
            for (int i = 0; i < 8; i++) results.add(pool.submit(() -> { start.await(); return VehicleJsonCache.parse(raw, admission); }));
            start.countDown(); shared = results.getFirst().get();
            for (var result : results) assertSame(shared, result.get());
        }
        VehicleJsonCache.finishRegistration();
        JsonObject replacement = VehicleJsonCache.parse(raw, admission);
        assertNotSame(shared, replacement); assertEquals(shared, replacement);
        VehicleJsonCache.beginReload(); assertNotSame(replacement, VehicleJsonCache.parse(raw, admission));
        assertEquals(0, admission.active()); VehicleJsonCache.finishRegistration();
    }
    @Test void oversizeAndInterruptedJsonRequestsReleaseAdmissionAndAllowRetry() {
        VehicleJsonCache.beginReload(); var admission = new ReadAdmission(1, 20);
        assertThrows(IllegalStateException.class, () -> VehicleJsonCache.parse("{\"value\":\"" + "a".repeat(30) + "\"}", admission));
        Thread.currentThread().interrupt();
        try { assertThrows(CancellationException.class, () -> VehicleJsonCache.parse("{}", admission)); }
        finally { Thread.interrupted(); }
        assertEquals("ok", VehicleJsonCache.parse("{\"value\":\"ok\"}", admission).get("value").getAsString());
        assertEquals(0, admission.active()); VehicleJsonCache.finishRegistration();
    }
}
