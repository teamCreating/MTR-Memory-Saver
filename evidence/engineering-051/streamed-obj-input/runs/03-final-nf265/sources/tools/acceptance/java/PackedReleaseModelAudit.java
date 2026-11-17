package site.benli06.audit;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.lang.reflect.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;
import net.minecraft.resources.ResourceLocation;
import org.mtr.core.serializer.JsonReader;
import org.mtr.libraries.com.google.gson.*;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;
import org.mtr.model.*;
import org.mtr.resource.*;
import site.benli06.*;

/** Runs the unmodified NeoForge release parser, then audits packed groups and merges. */
public final class PackedReleaseModelAudit {
    private static Object field(Object object, Class<?> owner, String name) throws Exception {
        Field f = owner.getDeclaredField(name); f.setAccessible(true); return f.get(object);
    }
    @SuppressWarnings("unchecked")
    private static JsonObject audit(JsonObject job) throws Exception {
        byte[] raw;
        try (ZipFile archive = new ZipFile(job.get("archive").getAsString())) {
            raw = archive.getInputStream(archive.getEntry(job.get("model").getAsString())).readAllBytes();
        }
        String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));
        if (!hash.equals(job.get("sha256").getAsString())) throw new AssertionError("Model fingerprint changed");
        BlockbenchModelLoader loader = new BlockbenchModelLoader(CustomResourceTools.formatIdentifierWithDefault(job.get("texture").getAsString(), "png"));
        loader.loadModel(() -> new BlockbenchModel(new JsonReader(JsonParser.parseString(new String(raw, StandardCharsets.UTF_8)))));
        if (!ModelLoaderBase.awaitParsing(60000) || !(boolean) field(loader, ModelLoaderBase.class, "modelLoaded"))
            throw new AssertionError("Release parsing failed or timed out");
        Map<String, NewOptimizedModelGroup> groups = (Map<String, NewOptimizedModelGroup>) field(loader, ModelLoaderBase.class, "nameToNewOptimizedModelGroup");
        long vertices = 0, payloadBytes = 0, boxes = 0;
        int meshes = 0;
        // Audit every actual parsed group, including ones not selected by this vehicle.
        for (NewOptimizedModelGroup group : groups.values()) {
            PackedModelGroupStore<ResourceLocation> packed = new PackedModelGroupStore<>();
            for (var stage : PackedMeshAudit.groups(group).entrySet()) for (var texture : stage.getValue().entrySet()) {
                packed.add(stage.getKey(), texture.getKey(), texture.getValue());
                vertices += texture.getValue().size(); meshes++;
                payloadBytes += packed.groups().get(stage.getKey()).get(texture.getKey()).payloadBytes();
                // Compare automatic bounds against an independent call to release add.
                var reference = new NewOptimizedModelGroup();
                var boundsStore = new PackedModelGroupStore<ResourceLocation>();
                var actualBoxes = new ObjectArrayList<net.minecraft.world.phys.AABB>();
                reference.add(stage.getKey(), texture.getKey(), list -> list.addAll(texture.getValue()), null);
                PackedModelGroupOperations.add(boundsStore, actualBoxes, stage.getKey(), texture.getKey(), list -> list.addAll(texture.getValue()), null);
                if (!reference.boxes.equals(actualBoxes)) throw new AssertionError("Parsed mesh bounds differ");
                boxes += actualBoxes.size();
            }
            PackedMeshAudit.compareGroup(group, packed);
            for (boolean mirror : new boolean[]{false, true}) {
                NewOptimizedModelGroup merged = new NewOptimizedModelGroup();
                PackedModelGroupStore<ResourceLocation> mergedPacked = new PackedModelGroupStore<>();
                merged.merge(group, RenderStage.EXTERIOR, 2.3, -0.0, -5.625, mirror);
                mergedPacked.merge(packed, RenderStage.EXTERIOR, 2.3, -0.0, -5.625, mirror);
                // Model coordinates are finite: transformations must match raw bits too.
                PackedMeshAudit.compareGroup(merged, mergedPacked);
                if (!merged.boxes.isEmpty()) throw new AssertionError("Release merge copied boxes");
            }
        }
        if (vertices == 0 || groups.isEmpty()) throw new AssertionError("No release-parsed geometry audited");
        JsonObject result = new JsonObject();
        result.addProperty("model_sha256", hash); result.addProperty("groups", groups.size());
        result.addProperty("meshes", meshes); result.addProperty("vertices", vertices);
        result.addProperty("packed_payload_bytes", payloadBytes); result.addProperty("bounds_compared", boxes);
        result.addProperty("mismatches", 0); result.addProperty("mirrored_and_ordinary_merge_checked", true);
        return result;
    }
    public static void main(String[] args) throws Exception {
        JsonArray jobs = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonArray();
        JsonObject results = new JsonObject();
        for (JsonElement value : jobs) {
            JsonObject job = value.getAsJsonObject();
            results.add(job.get("key").getAsString(), audit(job));
            Files.writeString(Path.of(args[1]), new GsonBuilder().setPrettyPrinting().create().toJson(results) + "\n");
            System.out.println("Verified release-parsed packed model " + results.size() + "/" + jobs.size() + ": " + job.get("key").getAsString());
        }
        try {
            Object statistics = PackedVertices.class.getMethod("sharingStatistics").invoke(null);
            Path output = Path.of(args[1]);
            Path sharing = output.resolveSibling(output.getFileName().toString().replaceFirst("\\.json$", "") + ".sharing.json");
            Files.writeString(sharing, new GsonBuilder().setPrettyPrinting().create().toJson(statistics) + "\n");
        } catch (NoSuchMethodException ignored) { /* Earlier candidates have no block pool. */ }
    }
}
