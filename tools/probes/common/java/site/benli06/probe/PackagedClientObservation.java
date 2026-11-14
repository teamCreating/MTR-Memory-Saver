package site.benli06.probe;

import com.mojang.blaze3d.systems.RenderSystem;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.OffsetDateTime;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import net.neoforged.neoforge.common.NeoForge;
import org.mtr.MTR;
import org.mtr.client.CustomResourceLoader;
import org.mtr.core.data.TransportMode;
import org.mtr.libraries.com.google.gson.JsonNull;
import org.mtr.libraries.com.google.gson.JsonObject;
import org.mtr.model.ModelLoaderBase;
import site.benli06.ReadAdmission;
import site.benli06.SharedBlockbenchCache;

/** Low-frequency observations belong only to the independent acceptance JAR. */
@Mod(value = "mtr_packaged_client_observer", dist = Dist.CLIENT)
public final class PackagedClientObservation {
    private static final boolean ENABLED = Boolean.getBoolean("mtr.memory.acceptance");
    private static final Object OUTPUT_LOCK = new Object();
    private static final ThreadLocal<ArrayDeque<Long>> RELOAD_CALLS = ThreadLocal.withInitial(ArrayDeque::new);
    private static final AtomicInteger NATIVE_PENDING = nativePendingCounter();
    private static final StackWalker STACK_WALKER = StackWalker.getInstance();
    private static long started, completed, lastCompletedSequence;
    private static int maxNesting;
    private long lastSample;
    private boolean writeFailureReported;

    public PackagedClientObservation() {
        if (!ENABLED) throw new IllegalStateException("Enable the isolated acceptance probe with -Dmtr.memory.acceptance=true");
        NeoForge.EVENT_BUS.addListener(this::tick);
    }

    private static AtomicInteger nativePendingCounter() {
        try {
            Field field = ModelLoaderBase.class.getDeclaredField("PENDING_PARSE_COUNT");
            field.setAccessible(true);
            return (AtomicInteger) field.get(null);
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    private void tick(ClientTickEvent.Post ignored) {
        long now = System.nanoTime();
        if (lastSample != 0 && now - lastSample < TimeUnit.SECONDS.toNanos(1)) return;
        lastSample = now;
        try {
            var mc = Minecraft.getInstance();
            JsonObject value = new JsonObject();
            value.addProperty("schema_version", 2);
            value.addProperty("timestamp", OffsetDateTime.now().toString());
            value.addProperty("monotonic_nanos", now);
            value.addProperty("pid", ProcessHandle.current().pid());
            value.addProperty("paused", mc.isPaused());
            value.addProperty("in_world", mc.level != null);
            if (mc.screen == null) value.add("screen", JsonNull.INSTANCE);
            else value.addProperty("screen", mc.screen.getClass().getName());
            if (mc.level == null) value.add("game_time", JsonNull.INSTANCE);
            else value.addProperty("game_time", mc.level.getGameTime());

            var heapUsage = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
            JsonObject heap = new JsonObject();
            heap.addProperty("used_bytes", heapUsage.getUsed());
            heap.addProperty("committed_bytes", heapUsage.getCommitted());
            heap.addProperty("max_bytes", heapUsage.getMax());
            value.add("heap", heap);

            var stats = SharedBlockbenchCache.statistics();
            JsonObject shared = new JsonObject();
            shared.addProperty("requests", stats.requests());
            shared.addProperty("path_hits", stats.pathHits());
            shared.addProperty("unique_parses", stats.uniqueParses());
            shared.addProperty("failures", stats.failures());
            shared.addProperty("pending", stats.pending());
            shared.addProperty("outstanding", stats.outstanding());
            shared.addProperty("queued", stats.queued());
            shared.addProperty("paths", stats.paths());
            shared.addProperty("content_keys", stats.contents());
            value.add("shared_blockbench", shared);
            value.addProperty("active_read_permits", ReadAdmission.GLOBAL.active());
            long[] workspaceStats = ReadAdmission.GLOBAL.workspaceStatistics();
            JsonObject workspace = new JsonObject();
            workspace.addProperty("budget_bytes", workspaceStats[0]);
            workspace.addProperty("used_bytes", workspaceStats[1]);
            workspace.addProperty("peak_bytes", workspaceStats[2]);
            workspace.addProperty("waiting", workspaceStats[3]);
            value.add("text_workspace", workspace);

            long awaitStarted = System.nanoTime();
            value.addProperty("native_settled", ModelLoaderBase.awaitParsing(1));
            value.addProperty("native_settled_probe_nanos", System.nanoTime() - awaitStarted);
            value.addProperty("native_pending", NATIVE_PENDING.get());
            var registeredIds = new HashSet<String>();
            for (TransportMode mode : TransportMode.values()) CustomResourceLoader.iterateVehicles(mode, vehicle -> registeredIds.add(vehicle.getId()));
            value.addProperty("registered_count", registeredIds.size());

            synchronized (OUTPUT_LOCK) {
                JsonObject epochs = new JsonObject();
                epochs.addProperty("started", started);
                epochs.addProperty("completed", completed);
                // Unreturned HEAD records remain visible, including an exceptional reload exit.
                epochs.addProperty("in_flight", started - completed);
                epochs.addProperty("max_nesting", maxNesting);
                epochs.addProperty("last_completed_sequence", lastCompletedSequence);
                value.add("resource_epochs", epochs);
                writeAtomic(directory().resolve("packaged-observer.json"), value);
            }
            writeFailureReported = false;
        } catch (Exception error) {
            if (!writeFailureReported) MTR.LOGGER.error("Cannot record packaged-client acceptance observations", error);
            writeFailureReported = true;
        }
    }

    /** Invoked only by the separate Mixin on the real reload invocation. */
    public static void reloadStarted() {
        if (!ENABLED) return;
        int nesting = reloadNesting();
        synchronized (OUTPUT_LOCK) {
            var calls = RELOAD_CALLS.get();
            // An exceptional exit has no RETURN injection; its start stays unpaired in the log.
            while (calls.size() >= nesting && !calls.isEmpty()) calls.removeLast();
            long sequence = ++started;
            calls.addLast(sequence);
            maxNesting = Math.max(maxNesting, nesting);
            appendEpoch("start", sequence, nesting);
        }
    }

    /** RETURN is method completion only; the periodic sample proves later ownership settlement. */
    public static void reloadReturned() {
        if (!ENABLED) return;
        int nesting = reloadNesting();
        synchronized (OUTPUT_LOCK) {
            var calls = RELOAD_CALLS.get();
            Long sequence = calls.pollLast();
            if (calls.isEmpty()) RELOAD_CALLS.remove();
            if (sequence != null) {
                completed++;
                lastCompletedSequence = sequence;
            }
            appendEpoch("return", sequence, nesting);
        }
    }

    private static int reloadNesting() {
        return STACK_WALKER.walk(frames -> (int) frames.filter(frame -> frame.getClassName().equals(CustomResourceLoader.class.getName())
                && frame.getMethodName().equals("reload")).count());
    }

    private static void appendEpoch(String phase, Long sequence, int nesting) {
        JsonObject event = new JsonObject();
        event.addProperty("schema_version", 1);
        event.addProperty("phase", phase);
        if (sequence == null) event.add("sequence", JsonNull.INSTANCE);
        else event.addProperty("sequence", sequence);
        event.addProperty("timestamp", OffsetDateTime.now().toString());
        event.addProperty("monotonic_nanos", System.nanoTime());
        event.addProperty("pid", ProcessHandle.current().pid());
        event.addProperty("thread", Thread.currentThread().getName());
        event.addProperty("thread_id", Thread.currentThread().threadId());
        event.addProperty("render_thread", RenderSystem.isOnRenderThread());
        event.addProperty("nesting", nesting);
        event.addProperty("in_flight", started - completed);
        event.addProperty("started", started);
        event.addProperty("completed", completed);
        try {
            Files.writeString(directory().resolve("resource-epochs.jsonl"), event + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (Exception error) {
            MTR.LOGGER.error("Cannot record resource-reload acceptance observation", error);
        }
    }

    private static Path directory() throws java.io.IOException {
        Path directory = Minecraft.getInstance().gameDirectory.toPath().resolve("game-probe");
        Files.createDirectories(directory);
        return directory;
    }

    private static void writeAtomic(Path destination, JsonObject value) throws java.io.IOException {
        Path temporary = destination.resolveSibling(destination.getFileName() + ".tmp");
        Files.writeString(temporary, value + "\n");
        try { Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
        catch (AtomicMoveNotSupportedException unsupported) { Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING); }
    }
}
