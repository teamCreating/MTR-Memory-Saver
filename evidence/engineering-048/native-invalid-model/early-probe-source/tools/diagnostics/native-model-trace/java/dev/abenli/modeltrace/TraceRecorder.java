package dev.abenli.modeltrace;

import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import org.mtr.MTR;
import org.mtr.libraries.com.google.gson.JsonArray;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Dedicated diagnostic only: no factory, model, cache, geometry or parser mutation. */
@Mod(value = "mtr_model_trace", dist = Dist.CLIENT)
public final class TraceRecorder {
    private static final AtomicLong SEQUENCE = new AtomicLong();
    private static final AtomicLong ERRORS = new AtomicLong();
    private static final Object LOCK = new Object();
    public TraceRecorder() { record("installed", null, null, false, null); }
    public static boolean unsupported(String model) {
        return model != null && !model.endsWith(".bbmodel") && !model.endsWith(".obj");
    }
    public static void record(String phase, String model, String texture, boolean flip, String resultClass) {
        try {
            JsonObject value = new JsonObject();
            value.addProperty("schema_version", 1); value.addProperty("phase", phase);
            value.addProperty("timestamp", Instant.now().toString()); value.addProperty("monotonic_nanos", System.nanoTime());
            value.addProperty("pid", ProcessHandle.current().pid());
            value.addProperty("process_started_at", ProcessHandle.current().info().startInstant().map(Instant::toString).orElse(null));
            value.addProperty("thread_id", Thread.currentThread().threadId()); value.addProperty("thread", Thread.currentThread().getName());
            value.addProperty("model_resource", model); value.addProperty("texture_resource", texture);
            value.addProperty("flip_texture_v", flip); value.addProperty("returned_loader_class", resultClass);
            JsonArray stack = new JsonArray();
            StackWalker.getInstance().forEach(frame -> {
                JsonObject location = new JsonObject(); location.addProperty("class", frame.getClassName());
                location.addProperty("method", frame.getMethodName()); location.addProperty("line", frame.getLineNumber());
                location.addProperty("bytecode_index", frame.getByteCodeIndex()); stack.add(location);
            });
            value.add("stack", stack);
            var target = TargetGuard.metadata(); value.add("target", target);
            synchronized (LOCK) {
                value.addProperty("sequence", SEQUENCE.incrementAndGet()); value.addProperty("observation_errors", ERRORS.get());
                var output = Minecraft.getInstance().gameDirectory.toPath().resolve(target.get("output").getAsString());
                Files.createDirectories(output.getParent());
                Files.writeString(output, value + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            }
        } catch (Exception failure) {
            ERRORS.incrementAndGet(); MTR.LOGGER.error("Native model diagnostic observation failed", failure);
        }
    }
}
