package dev.abenli.neutralprobe;

import com.mojang.blaze3d.systems.RenderSystem;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import org.mtr.libraries.com.google.gson.JsonArray;
import org.mtr.libraries.com.google.gson.JsonNull;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Native unsupported-format observations shared by both comparison treatments. */
public final class NativeModelDiagnostics {
    private static final Object LOCK = new Object();
    private static final DiagnosticTracker CALLS = new DiagnosticTracker();
    private static final AtomicLong ERRORS = new AtomicLong();
    private static final StackWalker WALKER = StackWalker.getInstance();
    private static long sequence;
    private NativeModelDiagnostics() {}

    public static void installed() { record("installed", null, null, false, null); }
    public static void beforeLog(String model, String texture, boolean flip) {
        record("before_native_invalid_log", model, texture, flip, null);
    }
    public static void returned(String model, String texture, boolean flip, String loaderClass) {
        record("native_fallback_return", model, texture, flip, loaderClass);
    }
    public static boolean unsupported(String model) {
        return model != null && !model.endsWith(".bbmodel") && !model.endsWith(".obj");
    }
    private static void record(String phase, String model, String texture, boolean flip, String loaderClass) {
        synchronized (LOCK) {
            try {
                JsonObject value = NativeObserver.diagnosticEnvelope(Instant.now(), System.nanoTime());
                var frames = WALKER.walk(stream -> stream.toList());
                int factoryNesting = (int) frames.stream().filter(frame -> frame.getClassName().equals("org.mtr.resource.VehicleModel")
                        && frame.getMethodName().equals("getModelLoaderBase")).count();
                int reloadNesting = (int) frames.stream().filter(frame -> frame.getClassName().equals("org.mtr.client.CustomResourceLoader")
                        && frame.getMethodName().equals("reload")).count();
                Thread thread = Thread.currentThread();
                var epoch = NativeObserver.activeEpoch(thread.threadId(), reloadNesting);
                Long epochId = epoch == null ? null : epoch.sequence();
                DiagnosticTracker.Call call = null;
                if (phase.equals("before_native_invalid_log"))
                    call = CALLS.begin(thread.threadId(), epochId, factoryNesting, model, texture, flip);
                else if (phase.equals("native_fallback_return")) {
                    call = CALLS.end(thread.threadId(), epochId, factoryNesting, model, texture, flip);
                    if (call == null) {
                        ERRORS.incrementAndGet();
                        NativeObserver.diagnosticFailure(new IllegalStateException("Native diagnostic return has no matching invocation"));
                    }
                }
                value.addProperty("phase", phase); value.addProperty("sequence", ++sequence);
                value.addProperty("thread_id", thread.threadId()); value.addProperty("thread", thread.getName());
                value.addProperty("render_thread", RenderSystem.isOnRenderThread());
                value.addProperty("native_factory_nesting", factoryNesting); value.addProperty("native_reload_nesting", reloadNesting);
                if (call == null) value.add("call_id", JsonNull.INSTANCE); else value.addProperty("call_id", call.id());
                if (epochId == null) value.add("epoch_id", JsonNull.INSTANCE); else value.addProperty("epoch_id", epochId);
                ObservationSchema.nullableString(value, "model_resource", model);
                ObservationSchema.nullableString(value, "texture_resource", texture);
                ObservationSchema.nullableString(value, "returned_loader_class", loaderClass);
                value.addProperty("flip_texture_v", flip);
                JsonArray stack = new JsonArray();
                for (var frame : frames) {
                    JsonObject location = new JsonObject();
                    location.addProperty("class", frame.getClassName()); location.addProperty("method", frame.getMethodName());
                    location.addProperty("descriptor", frame.getDescriptor()); location.addProperty("line", frame.getLineNumber());
                    location.addProperty("bytecode_index", frame.getByteCodeIndex()); stack.add(location);
                }
                value.add("stack", stack);
                value.addProperty("observation_errors", NativeObserver.observationErrorCount());
                value.add("native_model_diagnostics", snapshot());
                Files.writeString(NativeObserver.diagnosticsPath(), value + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (Exception failure) {
                ERRORS.incrementAndGet(); NativeObserver.diagnosticFailure(failure);
            }
        }
    }
    public static JsonObject snapshot() {
        var state = CALLS.state();
        JsonObject value = new JsonObject(); value.addProperty("started", state.started());
        value.addProperty("completed", state.completed()); value.addProperty("in_flight", state.inFlight());
        value.addProperty("observation_errors", ERRORS.get());
        return value;
    }
}
