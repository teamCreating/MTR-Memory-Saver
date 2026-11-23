package site.benli06;

import java.time.Duration;
import java.io.IOException;
import java.io.Reader;
import java.io.UncheckedIOException;
import java.util.function.Supplier;
import net.minecraft.resources.ResourceLocation;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.CompletionException;
import org.mtr.MTR;
import org.mtr.core.serializer.JsonReader;
import org.mtr.libraries.com.google.gson.JsonParser;
import org.mtr.model.BlockbenchModelLoader;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.BlockbenchModel;
import org.mtr.resource.CustomResourceTools;
import org.mtr.resource.ResourceProvider;

/** Path hits precede text reads/digests; admitted workers preserve the native mesh algorithm. */
public final class SharedBlockbenchCache {
    private record Content(String digest, String texture, boolean flipV) {}
    private static final class ParseCapture {
        final ModelLoaderBase source;
        boolean loaded;
        Throwable failure;
        ParseCapture(ModelLoaderBase source) { this.source = source; }
    }
    private static final ThreadLocal<ParseCapture> OWNED_PARSE = new ThreadLocal<>();
    private static final GenerationWorkCache<ResourceSourceKey, Content, ModelLoaderBase> CACHE = new GenerationWorkCache<>(
            ReadAdmission.positiveProperty("mtr.memory.parsers", 2),
            ReadAdmission.positiveProperty("mtr.memory.parseQueue", 64),
            Duration.ofSeconds(ReadAdmission.positiveProperty("mtr.memory.parseTimeoutSeconds", 300)),
            ReadAdmission.GLOBAL, ModelLoaderBase::parseStarted, ModelLoaderBase::parseFinished);
    private SharedBlockbenchCache() {}

    public static ModelLoaderBase get(String model, String texture, ResourceProvider provider, boolean flipV) {
        var modelId = CustomResourceTools.formatIdentifierWithDefault(model, "bbmodel");
        var textureId = CustomResourceTools.formatIdentifierWithDefault(texture, "png");
        Object identity = provider instanceof SnapshotResourceProvider snapshots ? snapshots.delegate() : provider;
        var key = new ResourceSourceKey(identity, modelId.toString(), textureId.toString(), flipV);
        var ready = CACHE.get(key, () -> prepare(modelId, textureId, provider, flipV));
        return new SharedBlockbenchLoader(textureId, ready, modelId.toString());
    }

    static GenerationWorkCache.Prepared<Content, ModelLoaderBase> prepare(ResourceLocation modelId, ResourceLocation textureId,
                                                                    ResourceProvider provider, boolean flipV) {
        if (provider instanceof SnapshotResourceProvider snapshots) {
            var captured = snapshots.snapshot(modelId);
            if (captured.isPresent()) {
                ResourceTextSnapshot snapshot = captured.get();
                try {
                    var content = new Content(snapshot.digest(), textureId.toString(), flipV);
                    return new GenerationWorkCache.Prepared<>(content, () -> load(modelId, textureId, () -> {
                        try (Reader reader = snapshot.reader()) { return parseInput(reader); }
                        catch (IOException error) { throw new UncheckedIOException(modelId.toString(), error); }
                    }), snapshot);
                } catch (Throwable error) {
                    try { snapshot.close(); }
                    catch (Throwable cleanup) { if (cleanup != error) error.addSuppressed(cleanup); }
                    throw error;
                }
            }
        }
        // Unknown providers, and the native DEBUG override, keep their exact String contract.
        String raw = provider.get(modelId);
        if (raw == null) throw new IllegalStateException("Missing Blockbench resource: " + modelId);
        ReadAdmission.GLOBAL.checkLength(raw.length());
        var content = new Content(digest(raw), textureId.toString(), flipV);
        return new GenerationWorkCache.Prepared<>(content, () -> load(modelId, textureId, () -> parseInput(raw)));
    }

    private static ModelLoaderBase load(ResourceLocation modelId, ResourceLocation textureId, Supplier<BlockbenchModel> input) {
        var source = new BlockbenchModelLoader(textureId);
        var capture = new ParseCapture(source);
        OWNED_PARSE.set(capture);
        try {
            source.loadModel(() -> {
                try { return input.get(); }
                catch (Throwable error) { capture.failure = error; throw error; }
            });
            if (!capture.loaded) throw new IllegalStateException("Native Blockbench parse ended without publication: " + modelId, capture.failure);
            return source;
        } finally { OWNED_PARSE.remove(); }
    }

    /** Only module-owned invocations are run inline, before their read scope is released. */
    public static Future<?> submitNative(ExecutorService executor, Runnable parse) {
        if (OWNED_PARSE.get() == null) return executor.submit(parse);
        var task = new FutureTask<Void>(parse, null);
        task.run();
        try { task.get(); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new CompletionException(error); }
        catch (java.util.concurrent.ExecutionException error) { throw new CompletionException(error.getCause()); }
        return task;
    }
    public static void completed(ModelLoaderBase source) {
        ParseCapture capture = OWNED_PARSE.get();
        if (capture != null && capture.source == source) capture.loaded = true;
    }
    public static void beginReload() { CACHE.beginReload(); SnapshotResourceProvider.beginReload(); }
    /** Keep the native parser, but never turn its malformed-input exception into a successful empty model. */
    static BlockbenchModel parseInput(String raw) {
        return new BlockbenchModel(new JsonReader(JsonParser.parseString(raw).getAsJsonObject()));
    }
    static BlockbenchModel parseInput(Reader reader) {
        return new BlockbenchModel(new JsonReader(JsonParser.parseReader(reader).getAsJsonObject()));
    }
    public static void finishRegistration() { CACHE.finishRegistration(); }
    public static GenerationWorkCache.Statistics statistics() { return CACHE.statistics(); }
    public static void report() {
        var stats = CACHE.statistics();
        MTR.LOGGER.info("MTR memory sharing: {} requests, {} path hits, {} unique parses, {} failures, {} pending, {} outstanding, {} queued",
                stats.requests(), stats.pathHits(), stats.uniqueParses(), stats.failures(), stats.pending(), stats.outstanding(), stats.queued());
        var inputs = SnapshotResourceProvider.statistics();
        MTR.LOGGER.info("MTR native resource snapshot capability: {} attempts, {} captures, {} String fallbacks, {} failures, {} decoded UTF-16 units",
                inputs.attempts(), inputs.captures(), inputs.stringFallbacks(), inputs.failures(), inputs.decodedCodeUnits());
    }
    private static String digest(String raw) { return ResourceTextDigest.sha256(raw); }
}
