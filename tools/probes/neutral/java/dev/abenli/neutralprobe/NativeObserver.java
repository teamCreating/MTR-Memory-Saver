package dev.abenli.neutralprobe;

import com.mojang.blaze3d.systems.RenderSystem;
import dev.abenli.neutralprobe.mixin.NativePendingAccess;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import net.neoforged.neoforge.client.event.RenderFrameEvent;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.tick.ServerTickEvent;
import org.mtr.MTR;
import org.mtr.libraries.com.google.gson.JsonNull;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Independent native observations; installing this JAR does not start JFR. */
@Mod(value = "mtr_native_observer", dist = Dist.CLIENT)
public final class NativeObserver {
    private static final Object OUTPUT_LOCK = new Object();
    private static final EpochTracker EPOCHS = new EpochTracker();
    private static final JsonObject PROCESS = ObservationSchema.processIdentity();
    private static final AtomicLong OBSERVATION_ERRORS = new AtomicLong();
    private static final StackWalker STACK_WALKER = StackWalker.getInstance();
    private static final JsonObject TARGET = targetMetadata();
    private static final JsonObject CAPABILITIES = capabilities();
    private long lastSample, previousFrame;
    private final ThreadLocal<Tick> ticks = new ThreadLocal<>();

    @Name("mtrtest.ClientFrame") @Label("Client render frame interval")
    @Enabled(true) @StackTrace(false) @Threshold("0 ns")
    public static final class Frame extends Event {
        public double intervalMs;
        public boolean inWorld;
        public boolean paused;
        public String screen;
    }
    @Name("mtrtest.ServerTick") @Label("NeoForge server tick event span")
    @Enabled(true) @StackTrace(false) @Threshold("0 ns")
    public static final class Tick extends Event {}

    public NativeObserver() {
        FlightRecorder.register(Frame.class);
        FlightRecorder.register(Tick.class);
        NeoForge.EVENT_BUS.addListener(this::sample);
        NeoForge.EVENT_BUS.addListener(this::frame);
        NeoForge.EVENT_BUS.addListener(this::beforeTick);
        NeoForge.EVENT_BUS.addListener(this::afterTick);
    }
    private static JsonObject targetMetadata() {
        try { return ObservationSchema.resource("/mtr-native-observer-target.json"); }
        catch (IOException failure) { throw new ExceptionInInitializerError(failure); }
    }
    private static JsonObject capabilities() {
        try { return ObservationSchema.resource("/capabilities.json").getAsJsonObject("capabilities"); }
        catch (IOException failure) { throw new ExceptionInInitializerError(failure); }
    }
    private void sample(ClientTickEvent.Post ignored) {
        long now = System.nanoTime();
        if (lastSample != 0 && now - lastSample < TimeUnit.SECONDS.toNanos(1)) return;
        lastSample = now;
        try {
            var mc = Minecraft.getInstance();
            JsonObject value = ObservationSchema.envelope(Instant.now(), now, PROCESS);
            value.add("target", TARGET.deepCopy());
            value.add("capabilities", CAPABILITIES.deepCopy());
            value.addProperty("paused", mc.isPaused());
            value.addProperty("in_world", mc.level != null);
            ObservationSchema.nullableString(value, "screen", mc.screen == null ? null : mc.screen.getClass().getName());
            if (mc.level == null) value.add("game_time", JsonNull.INSTANCE);
            else value.addProperty("game_time", mc.level.getGameTime());
            var usage = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
            JsonObject heap = new JsonObject();
            heap.addProperty("used_bytes", usage.getUsed());
            heap.addProperty("committed_bytes", usage.getCommitted());
            heap.addProperty("max_bytes", usage.getMax());
            value.add("heap", heap);
            var registry = NativeRegistry.capture();
            ObservationSchema.counts(value, registry.counts(), NativePendingAccess.neutralPending().get());
            NativeScene.capture(value, mc, registry);
            synchronized (OUTPUT_LOCK) {
                value.add("resource_epochs", ObservationSchema.epochs(EPOCHS.state()));
                value.addProperty("observation_errors", OBSERVATION_ERRORS.get());
                ObservationSchema.completedCapture(value, Instant.now(), System.nanoTime());
                writeAtomic(path("snapshot_path"), value);
            }
        } catch (Exception failure) { failure("snapshot", failure); }
    }
    private void frame(RenderFrameEvent.Pre ignored) {
        long now = System.nanoTime();
        if (previousFrame != 0) {
            Frame event = new Frame();
            if (event.isEnabled()) {
                var mc = Minecraft.getInstance();
                event.intervalMs = (now - previousFrame) / 1e6;
                event.inWorld = mc.level != null;
                event.paused = mc.isPaused();
                event.screen = mc.screen == null ? "game" : mc.screen.getClass().getName();
                event.commit();
            }
        }
        previousFrame = now;
    }
    private void beforeTick(ServerTickEvent.Pre ignored) {
        ticks.remove();
        Tick event = new Tick();
        if (event.isEnabled()) { event.begin(); ticks.set(event); }
    }
    private void afterTick(ServerTickEvent.Post ignored) {
        Tick event = ticks.get();
        if (event != null) { event.end(); event.commit(); ticks.remove(); }
    }
    public static void reloadStarted() { recordEpoch(true); }
    public static void reloadReturned() { recordEpoch(false); }
    private static void recordEpoch(boolean start) {
        Instant observedAt = Instant.now();
        long now = System.nanoTime();
        Thread thread = Thread.currentThread();
        int nesting = STACK_WALKER.walk(frames -> (int) frames.filter(frame ->
                frame.getClassName().equals("org.mtr.client.CustomResourceLoader") && frame.getMethodName().equals("reload")).count());
        synchronized (OUTPUT_LOCK) {
            try {
                var call = start ? EPOCHS.begin(thread.threadId(), nesting) : EPOCHS.end(thread.threadId(), nesting);
                JsonObject value = ObservationSchema.envelope(observedAt, now, PROCESS);
                value.addProperty("phase", start ? "start" : "return");
                value.addProperty("event", start ? "native_reload_head" : "native_reload_return");
                if (call == null) {
                    value.add("sequence", JsonNull.INSTANCE);
                    value.add("epoch_id", JsonNull.INSTANCE);
                    OBSERVATION_ERRORS.incrementAndGet();
                } else {
                    value.addProperty("sequence", call.sequence());
                    value.addProperty("epoch_id", call.sequence());
                }
                value.addProperty("thread", thread.getName());
                value.addProperty("thread_id", thread.threadId());
                value.addProperty("render_thread", RenderSystem.isOnRenderThread());
                value.addProperty("nesting", nesting);
                var state = ObservationSchema.epochs(EPOCHS.state());
                for (var field : state.entrySet()) value.add(field.getKey(), field.getValue());
                ObservationSchema.counts(value, NativeRegistry.capture().counts(), NativePendingAccess.neutralPending().get());
                value.addProperty("observation_errors", OBSERVATION_ERRORS.get());
                Files.writeString(path("epochs_path"), value + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (Exception failure) { failure("native epoch", failure); }
        }
    }
    private static Path path(String field) throws IOException {
        Path destination = Minecraft.getInstance().gameDirectory.toPath().resolve(TARGET.get(field).getAsString());
        Files.createDirectories(destination.getParent());
        return destination;
    }
    private static void writeAtomic(Path destination, JsonObject value) throws IOException {
        Path temporary = destination.resolveSibling(destination.getFileName() + ".tmp");
        Files.writeString(temporary, value + "\n");
        try { Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
        catch (AtomicMoveNotSupportedException unsupported) { Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING); }
    }
    private static void failure(String operation, Exception failure) {
        OBSERVATION_ERRORS.incrementAndGet();
        MTR.LOGGER.error("Cannot record native observer " + operation, failure);
    }
}
