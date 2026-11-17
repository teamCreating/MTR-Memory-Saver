package site.benli06.probe;

import java.lang.reflect.*;
import java.nio.file.*;
import java.time.OffsetDateTime;
import java.util.concurrent.CompletableFuture;
import com.mojang.blaze3d.vertex.VertexFormat;
import site.benli06.PackedModelGroupAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.mtr.model.*;
import org.mtr.resource.RenderStage;
import org.mtr.libraries.com.google.gson.*;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.*;

/** Disposable model/GPU ownership checks inside a marked isolated client. */
@Mod(value = "v6_memory_compatibility_probe", dist = Dist.CLIENT)
public final class V6MemoryCompatibilityProbe {
    private final Path instance;
    private boolean completed;

    public V6MemoryCompatibilityProbe() {
        instance = Minecraft.getInstance().gameDirectory.toPath();
        if (!Boolean.getBoolean("mtr.memory.acceptance")) throw new IllegalStateException("Enable the isolated acceptance probe with -Dmtr.memory.acceptance=true");
        NeoForge.EVENT_BUS.addListener(this::tick);
    }

    private void tick(ClientTickEvent.Post ignored) {
        if (completed || (Minecraft.getInstance().level == null && !Boolean.getBoolean("mtr.memory.acceptance.gpuAtTitle"))
                || Minecraft.getInstance().getOverlay() != null
                || (Minecraft.getInstance().level != null && Minecraft.getInstance().screen != null)
                || !Files.isRegularFile(instance.resolve("v6-compatibility-request.json"))) return;
        completed = true;
        JsonObject report = new JsonObject();
        report.addProperty("timestamp", OffsetDateTime.now().toString());
        try {
            report.add("request", JsonParser.parseString(Files.readString(instance.resolve("v6-compatibility-request.json"))));
            int iterations = site.benli06.ReadAdmission.positiveProperty("mtr.memory.acceptance.gpuIterations", 1);
            JsonArray checks = new JsonArray();
            for (int i = 0; i < iterations; i++) checks.add(audit());
            report.add("checks", checks);
            report.addProperty("iterations", iterations);
            report.addProperty("passed", true);
        } catch (Throwable error) {
            report.addProperty("passed", false);
            report.addProperty("error", error.toString());
            java.io.StringWriter trace = new java.io.StringWriter();
            error.printStackTrace(new java.io.PrintWriter(trace));
            report.addProperty("stack", trace.toString());
        }
        try { Files.writeString(instance.resolve("v6-compatibility-result.json"), report + "\n", java.nio.file.StandardOpenOption.CREATE_NEW); }
        catch (Exception error) { throw new RuntimeException(error); }
        if (Boolean.getBoolean("mtr.memory.acceptance.exit")) Minecraft.getInstance().stop();
    }

    private static Object field(Object target, Class<?> owner, String name) throws Exception {
        Field field = owner.getDeclaredField(name);
        field.setAccessible(true);
        return field.get(target);
    }

    private static void check(JsonObject report, String name, boolean passed) {
        if (!passed) throw new AssertionError(name);
        report.addProperty(name, true);
    }

    private static NewOptimizedModelGroup sourceGroup() {
        var group = new NewOptimizedModelGroup();
        var texture = ResourceLocation.fromNamespaceAndPath("minecraft", "textures/block/white_concrete.png");
        group.add(null, texture, vertices -> {
            vertices.add(new StoredVertexData(0, 0, 0, 0x80123456, 0, 0, 0, 0, 1));
            vertices.add(new StoredVertexData(1, 0, 0, 0xff123456, 1, 0, 0, 0, 1));
            vertices.add(new StoredVertexData(1, 1, 0, 0x00123456, 1, 1, 0, 0, 1));
            vertices.add(new StoredVertexData(0, 1, 0, 0xffffffff, 0, 1, 0, 0, 1));
        }, null);
        return group;
    }

    private static final class Source extends ModelLoaderBase {
        Source(NewOptimizedModelGroup group) {
            super(ResourceLocation.fromNamespaceAndPath("minecraft", "textures/block/white_concrete.png"), VertexFormat.Mode.QUADS);
            addModel("body", group);
            setModelLoaded();
        }
    }

    private static ModelLoaderBase facade(CompletableFuture<ModelLoaderBase> source) throws Exception {
        Constructor<?> constructor = Class.forName("site.benli06.SharedBlockbenchLoader")
                .getDeclaredConstructor(ResourceLocation.class, CompletableFuture.class);
        constructor.setAccessible(true);
        return (ModelLoaderBase) constructor.newInstance(ResourceLocation.fromNamespaceAndPath("minecraft", "textures/block/white_concrete.png"), source);
    }

    private static JsonObject audit() throws Exception {
        JsonObject checks = new JsonObject();
        NewOptimizedModelGroup sourceGroup = sourceGroup(), destination = new NewOptimizedModelGroup();
        var packed = (PackedModelGroupAccess<?>) (Object) destination;
        destination.merge(sourceGroup, RenderStage.EXTERIOR, .25, 0, -.5, false);
        var models = destination.build(VertexFormat.Mode.QUADS);
        try {
            check(checks, "repeated_build_reuses_native_map", models == destination.build(VertexFormat.Mode.QUADS));
            check(checks, "native_built_models_field_set", field(destination, NewOptimizedModelGroup.class, "builtModels") == models);
            check(checks, "built_destination_releases_packed_staging", packed.packedMeshStore().groups().isEmpty());
            check(checks, "shared_source_staging_retained", !((PackedModelGroupAccess<?>) (Object) sourceGroup).packedMeshStore().groups().isEmpty());
            boolean rejected = false;
            try { destination.add(null, null, values -> {}, null); }
            catch (IllegalStateException expected) { rejected = true; }
            check(checks, "add_after_build_rejected", rejected);
            rejected = false;
            try { destination.merge(sourceGroup, RenderStage.EXTERIOR, 0, 0, 0, false); }
            catch (IllegalStateException expected) { rejected = true; }
            check(checks, "merge_after_build_rejected", rejected);
        } finally { models.values().forEach(list -> list.forEach(NewOptimizedModel::close)); }

        CompletableFuture<ModelLoaderBase> ready = new CompletableFuture<>();
        ModelLoaderBase closedEarly = facade(ready), first = facade(ready), second = facade(ready);
        Source source = new Source(sourceGroup);
        try {
            closedEarly.close();
            ready.complete(source);
            check(checks, "closed_facade_not_repopulated", ((java.util.Map<?, ?>) field(closedEarly, ModelLoaderBase.class, "nameToNewOptimizedModelGroup")).isEmpty());
            check(checks, "closed_facade_not_marked_loaded", !((Boolean) field(closedEarly, ModelLoaderBase.class, "modelLoaded")));
            var firstModels = first.get();
            var secondModels = second.get();
            NewOptimizedModel firstModel = firstModels.values().iterator().next().getFirst();
            NewOptimizedModel secondModel = secondModels.values().iterator().next().getFirst();
            check(checks, "facades_have_independent_gpu_models", firstModel != secondModel);
            first.close();
            check(checks, "closed_facade_disposes_own_gpu_model", (Boolean) field(firstModel, NewOptimizedModel.class, "closed"));
            check(checks, "other_facade_gpu_model_still_open", !((Boolean) field(secondModel, NewOptimizedModel.class, "closed")));
            check(checks, "other_facade_remains_cached", second.get() == secondModels);
        } finally { closedEarly.close(); first.close(); second.close(); source.close(); }
        return checks;
    }
}
