package dev.abenli.mtrmemory;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.atomic.LongAdder;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.mtr.MTR;
import org.mtr.core.serializer.JsonReader;
import org.mtr.core.tool.Utilities;
import org.mtr.model.BlockbenchModelLoader;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.BlockbenchModel;
import org.mtr.resource.CustomResourceTools;
import org.mtr.resource.ResourceProvider;

/** Shares parsed mesh inputs; each vehicle keeps its own property-dependent build. */
public final class SharedBlockbenchCache {
    private record Selection(boolean all, Set<String> names) {}
    private record Key(String content, String texture, boolean flipV, Selection selection) {}
    private record Entry(CompletableFuture<ModelLoaderBase> ready, int epoch, Selection selection) {}
    private static final Selection ALL = new Selection(true, Set.of());
    private static final ConcurrentHashMap<Key, Entry> CACHE = new ConcurrentHashMap<>();
    private static final IdentityHashMap<ModelLoaderBase, Entry> PENDING = new IdentityHashMap<>();
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static final AtomicInteger COMPLETED = new AtomicInteger();
    private static final AtomicInteger UNIQUE = new AtomicInteger();
    private static final AtomicInteger EPOCH = new AtomicInteger();
    private static final LongAdder RETAINED_DISPLAYS = new LongAdder(), SKIPPED_DISPLAYS = new LongAdder();

    private SharedBlockbenchCache() {}

    public static ModelLoaderBase get(String model, String texture, ResourceProvider provider, boolean flipV) {
        REQUESTS.incrementAndGet();
        var textureId = CustomResourceTools.formatIdentifierWithDefault(texture, "png");
        return new SharedBlockbenchLoader(textureId, source(model, texture, provider, flipV, ALL));
    }

    /** Vehicle constructors configure actual DISPLAY names before native parse submission. */
    public static ModelLoaderBase getForVehicle(String model, String texture, ResourceProvider provider, boolean flipV) {
        REQUESTS.incrementAndGet();
        var textureId = CustomResourceTools.formatIdentifierWithDefault(texture, "png");
        return new SharedBlockbenchLoader(textureId, names -> source(model, texture, provider, flipV,
                new Selection(false, Set.copyOf(names))));
    }

    private static CompletableFuture<ModelLoaderBase> source(String model, String texture, ResourceProvider provider,
                                                              boolean flipV, Selection selection) {
        String raw = provider.get(CustomResourceTools.formatIdentifierWithDefault(model, "bbmodel"));
        var textureId = CustomResourceTools.formatIdentifierWithDefault(texture, "png");
        Key key = new Key(digest(raw), textureId.toString(), flipV, selection);
        Entry entry = CACHE.computeIfAbsent(key, ignored -> {
            BlockbenchModelLoader source = new BlockbenchModelLoader(textureId);
            Entry created = new Entry(new CompletableFuture<>(), EPOCH.get(), selection);
            UNIQUE.incrementAndGet();
            synchronized (PENDING) { PENDING.put(source, created); }
            try { source.loadModel(() -> new BlockbenchModel(new JsonReader(Utilities.parseJson(raw)))); }
            catch (RuntimeException | Error error) {
                synchronized (PENDING) { PENDING.remove(source); }
                created.ready().completeExceptionally(error);
                throw error;
            }
            return created;
        });
        return entry.ready();
    }

    public static boolean retainDisplay(ModelLoaderBase source, String name, int parts) {
        Entry entry;
        synchronized (PENDING) { entry = PENDING.get(source); }
        if (entry == null) return true;
        boolean keep = entry.selection().all() || entry.selection().names().contains(name);
        if (entry.epoch() == EPOCH.get()) (keep ? RETAINED_DISPLAYS : SKIPPED_DISPLAYS).add(parts);
        return keep;
    }

    /** Runs at native parseFinished; successful setModelLoaded already removed its entry. */
    public static void finishParseAttempt(ModelLoaderBase source) {
        Entry failed;
        synchronized (PENDING) { failed = PENDING.remove(source); }
        if (failed != null) failed.ready().completeExceptionally(
                new IllegalStateException("Native Blockbench parsing did not complete; see the original MTR parser log"));
    }

    public static void completed(ModelLoaderBase source) {
        Entry entry;
        synchronized (PENDING) { entry = PENDING.remove(source); }
        if (entry != null) {
            if (entry.epoch() == EPOCH.get() && COMPLETED.incrementAndGet() % 100 == 0) report();
            entry.ready().complete(source);
        }
    }

    public static void beginReload() {
        // In-flight older sources retain their own completion entries until finished.
        CACHE.clear();
        EPOCH.incrementAndGet();
        REQUESTS.set(0);
        COMPLETED.set(0);
        UNIQUE.set(0);
        RETAINED_DISPLAYS.reset(); SKIPPED_DISPLAYS.reset();
    }

    public static void report() {
        MTR.LOGGER.info("MTR memory sharing: {} Blockbench requests, {} unique parses, {} completed",
                REQUESTS.get(), UNIQUE.get(), COMPLETED.get());
    }

    /** Completed facades own their inputs; pending parses keep their completion entry. */
    public static void finishRegistration() {
        int entries = CACHE.size();
        CACHE.clear();
        MTR.LOGGER.info("MTR memory sharing: released {} shared source loaders after registration", entries);
        MTR.LOGGER.info("MTR source display retention: {} retained / {} skipped raw display parts during parsing",
                RETAINED_DISPLAYS.sum(), SKIPPED_DISPLAYS.sum());
    }

    private static String digest(String raw) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }
}
