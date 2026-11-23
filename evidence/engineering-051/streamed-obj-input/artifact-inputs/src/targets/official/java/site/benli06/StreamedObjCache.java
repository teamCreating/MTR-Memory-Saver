package site.benli06;

import java.io.InputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CancellationException;
import java.util.function.Function;
import net.minecraft.resources.ResourceLocation;
import org.apache.commons.io.IOUtils;
import org.mtr.MTR;
import org.mtr.model.ModelLoaderBase;
import org.mtr.model.ObjModelLoader;
import org.mtr.resource.CustomResourceTools;
import org.mtr.resource.ResourceProvider;
import org.mtr.libraries.de.javagl.obj.Obj;
import org.mtr.libraries.de.javagl.obj.ObjReader;
import org.mtr.libraries.de.javagl.obj.Mtl;
import org.mtr.libraries.de.javagl.obj.MtlReader;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;

/** Admits descriptors before reading OBJ input; material dependencies are not content-aliased. */
public final class StreamedObjCache {
    private static final GenerationWorkCache<ResourceSourceKey, ResourceSourceKey, ModelLoaderBase> CACHE =
            new GenerationWorkCache<>(ReadAdmission.positiveProperty("mtr.memory.parsers", 2),
                    ReadAdmission.positiveProperty("mtr.memory.parseQueue", 64),
                    Duration.ofSeconds(ReadAdmission.positiveProperty("mtr.memory.parseTimeoutSeconds", 300)),
                    ReadAdmission.GLOBAL, ModelLoaderBase::parseStarted, ModelLoaderBase::parseFinished);
    private StreamedObjCache() {}

    public static ModelLoaderBase get(String model, String texture, SnapshotResourceProvider provider, boolean flipV) {
        var defaultTexture = CustomResourceTools.formatIdentifierWithDefault(texture, "png");
        var modelId = CustomResourceTools.formatIdentifierWithDefault(model, "obj");
        var key = new ResourceSourceKey(provider.delegate(), model, texture, flipV);
        var future = CACHE.get(key, () -> {
            var captured = provider.snapshot(modelId);
            if (captured.isPresent()) {
                var snapshot = captured.get();
                try {
                    return new GenerationWorkCache.Prepared<>(key,
                            () -> load(snapshot, null, model, defaultTexture, provider, flipV), snapshot);
                } catch (Throwable error) {
                    try { snapshot.close(); }
                    catch (Throwable close) { if (close != error) error.addSuppressed(close); }
                    throw error;
                }
            }
            String raw = provider.get(modelId);
            if (raw == null) throw new IllegalStateException("Missing OBJ resource: " + modelId);
            ReadAdmission.GLOBAL.checkLength(raw.length());
            return new GenerationWorkCache.Prepared<>(key, () -> load(null, raw, model, defaultTexture, provider, flipV));
        });
        return new SharedObjLoader(defaultTexture, future, modelId.toString());
    }

    private static ModelLoaderBase load(ResourceTextSnapshot snapshot, String raw, String model,
                                        ResourceLocation defaultTexture, SnapshotResourceProvider provider, boolean flipV) {
        try {
            Obj obj;
            try (InputStream input = snapshot == null ? IOUtils.toInputStream(raw, StandardCharsets.UTF_8) : snapshot.utf8Stream()) {
                // Keep the native InputStream entry point, including its US-ASCII decoding.
                obj = ObjReader.read(input);
            }
            // Geometry no longer uses the source. A close failure must precede publication.
            if (snapshot != null) snapshot.close();
            var materials = materials(obj, model, provider);
            Function<String, ResourceLocation> textures = name -> texture(model, defaultTexture, name);
            var source = new ObjModelLoader(defaultTexture);
            ((ObjModelAssembly) (Object) source).assemble(obj, materials, textures, flipV);
            return source;
        } catch (IOException error) { throw new UncheckedIOException(model, error); }
    }

    static Object2ObjectOpenHashMap<String, Mtl> materials(Obj obj, String model, SnapshotResourceProvider provider) {
        var result = new Object2ObjectOpenHashMap<String, Mtl>();
        for (String name : obj.getMtlFileNames()) {
            try {
                var id = CustomResourceTools.getResourceFromSamePath(model, materialPath(name), "mtl");
                var captured = provider.snapshot(id);
                if (captured.isPresent()) {
                    try (var snapshot = captured.get(); var input = snapshot.utf8Stream()) {
                        for (Mtl material : MtlReader.read(input)) result.put(material.getName(), material);
                    }
                } else {
                    String raw = provider.get(id);
                    if (raw != null) ReadAdmission.GLOBAL.checkLength(raw.length());
                    try (var input = IOUtils.toInputStream(raw, StandardCharsets.UTF_8)) {
                        for (Mtl material : MtlReader.read(input)) result.put(material.getName(), material);
                    }
                }
            } catch (CancellationException error) { throw error; }
            catch (Exception error) {
                // Native MTL parsing logs an Exception and continues; Errors still escape.
                MTR.LOGGER.error("Failed to parse MTL file [{}] referenced by OBJ model", name, error);
            }
        }
        return result;
    }

    static String materialPath(String name) { return name.replace("\\\\", "/").replace("\\", "/"); }
    static ResourceLocation texture(String model, ResourceLocation fallback, String name) {
        if (name == null || name.isEmpty()) return ResourceLocation.fromNamespaceAndPath("mtr", "textures/block/white.png");
        return name.equals("default.png") ? fallback : CustomResourceTools.getResourceFromSamePath(model, name, "png");
    }
    public static void beginReload() { CACHE.beginReload(); }
    public static void finishRegistration() { CACHE.finishRegistration(); }
    public static GenerationWorkCache.Statistics statistics() { return CACHE.statistics(); }
    public static void report() {
        var s = CACHE.statistics();
        MTR.LOGGER.info("MTR streamed OBJ: {} requests, {} path hits, {} parses, {} failures, {} pending, {} outstanding, {} queued",
                s.requests(), s.pathHits(), s.uniqueParses(), s.failures(), s.pending(), s.outstanding(), s.queued());
    }
}
