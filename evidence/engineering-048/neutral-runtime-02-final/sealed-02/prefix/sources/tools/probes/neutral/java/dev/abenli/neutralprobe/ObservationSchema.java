package dev.abenli.neutralprobe;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.mtr.libraries.com.google.gson.JsonNull;
import org.mtr.libraries.com.google.gson.JsonObject;
import org.mtr.libraries.com.google.gson.JsonParser;

public final class ObservationSchema {
    private ObservationSchema() {}
    public static JsonObject resource(String path) throws IOException {
        try (var input = ObservationSchema.class.getResourceAsStream(path)) {
            if (input == null) throw new IOException("Missing observer metadata: " + path);
            return JsonParser.parseString(new String(input.readAllBytes(), StandardCharsets.UTF_8)).getAsJsonObject();
        }
    }
    public static JsonObject envelope(Instant observedAt, long monotonicNanos, JsonObject process) {
        JsonObject result = new JsonObject();
        result.addProperty("schema_version", 1);
        result.addProperty("probe_kind", "official-native-observer");
        result.addProperty("observed_at", observedAt.toString());
        result.addProperty("timestamp", observedAt.toString());
        result.addProperty("monotonic_nanos", monotonicNanos);
        result.add("process", process.deepCopy());
        result.add("pid", process.get("pid").deepCopy());
        result.add("process_created", process.get("start_instant").deepCopy());
        return result;
    }
    public static JsonObject processIdentity() {
        var current = ProcessHandle.current();
        var info = current.info();
        JsonObject value = new JsonObject();
        value.addProperty("pid", current.pid());
        value.add("start_instant", info.startInstant().map(instant ->
                new org.mtr.libraries.com.google.gson.JsonPrimitive(instant.toString())).orElse(null));
        value.add("executable", info.command().map(command ->
                new org.mtr.libraries.com.google.gson.JsonPrimitive(command)).orElse(null));
        value.addProperty("java_version", System.getProperty("java.version"));
        value.addProperty("java_runtime_version", System.getProperty("java.runtime.version"));
        value.addProperty("java_vendor", System.getProperty("java.vendor"));
        return value;
    }
    /** A settled read must not be attributed to the earlier capture start. */
    public static void completedCapture(JsonObject value, Instant completedAt, long completedNanos) {
        value.add("capture_started_at", value.get("observed_at").deepCopy());
        value.add("capture_started_monotonic_nanos", value.get("monotonic_nanos").deepCopy());
        value.addProperty("observed_at", completedAt.toString());
        value.addProperty("timestamp", completedAt.toString());
        value.addProperty("monotonic_nanos", completedNanos);
    }
    public static JsonObject epochs(EpochTracker.State state) {
        JsonObject value = new JsonObject();
        value.addProperty("started", state.started());
        value.addProperty("completed", state.completed());
        value.addProperty("in_flight", state.inFlight());
        value.addProperty("max_nesting", state.maxNesting());
        value.addProperty("last_completed_sequence", state.lastCompletedSequence());
        return value;
    }
    public static void counts(JsonObject result, RegistrationCounts counts, int pending) {
        result.addProperty("registered_count", counts.distinctIds());
        result.addProperty("registered_declarations", counts.declarations());
        result.addProperty("native_pending", pending);
        result.addProperty("native_settled", pending == 0);
    }
    public static void nullableString(JsonObject value, String field, String text) {
        if (text == null) value.add(field, JsonNull.INSTANCE); else value.addProperty(field, text);
    }
}
