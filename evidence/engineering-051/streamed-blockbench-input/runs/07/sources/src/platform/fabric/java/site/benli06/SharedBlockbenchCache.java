package site.benli06;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.class_2960;
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
    private record Key(String content, String texture, boolean flipV) {}
    private record Entry(CompletableFuture<ModelLoaderBase> ready, int epoch) {}
    private static final ConcurrentHashMap<Key, Entry> CACHE = new ConcurrentHashMap<>();
    private static final IdentityHashMap<ModelLoaderBase, Entry> PENDING = new IdentityHashMap<>();
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static final AtomicInteger COMPLETED = new AtomicInteger();
    private static final AtomicInteger EPOCH = new AtomicInteger();

    private SharedBlockbenchCache() {}

    public static ModelLoaderBase get(String model, String texture, ResourceProvider provider, boolean flipV) {
        String raw = provider.get(CustomResourceTools.formatIdentifierWithDefault(model, "bbmodel"));
        class_2960 textureId = CustomResourceTools.formatIdentifierWithDefault(texture, "png");
        Key key = new Key(digest(raw), textureId.toString(), flipV);
        REQUESTS.incrementAndGet();
        Entry entry = CACHE.computeIfAbsent(key, ignored -> {
            BlockbenchModelLoader source = new BlockbenchModelLoader(textureId);
            Entry created = new Entry(new CompletableFuture<>(), EPOCH.get());
            synchronized (PENDING) { PENDING.put(source, created); }
            source.loadModel(() -> new BlockbenchModel(new JsonReader(Utilities.parseJson(raw))));
            return created;
        });
        return new SharedBlockbenchLoader(textureId, entry.ready());
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
    }

    public static void report() {
        MTR.LOGGER.info("MTR memory sharing: {} Blockbench requests, {} unique parses, {} completed",
                REQUESTS.get(), CACHE.size(), COMPLETED.get());
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
