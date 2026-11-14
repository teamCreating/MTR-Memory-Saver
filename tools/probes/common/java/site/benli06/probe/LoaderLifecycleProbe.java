package site.benli06.probe;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.OffsetDateTime;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.client.event.ClientTickEvent;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.mtr.libraries.com.google.gson.JsonObject;
import site.benli06.ReadAdmission;
import site.benli06.SharedBlockbenchCache;
import site.benli06.mixin.ModelLoaderAccess;

/** Actual client-side Mixin smoke check; empty fixtures do not certify rendered geometry/GPU. */
@Mod(value = "mtr_memory_loader_probe", dist = Dist.CLIENT)
public final class LoaderLifecycleProbe {
    private final Path instance = Minecraft.getInstance().gameDirectory.toPath();
    private boolean completed;
    public LoaderLifecycleProbe() {
        if (!Boolean.getBoolean("mtr.memory.acceptance")) throw new IllegalStateException("Enable the isolated acceptance probe with -Dmtr.memory.acceptance=true");
        NeoForge.EVENT_BUS.addListener(this::tick);
    }
    private void tick(ClientTickEvent.Post ignored) {
        if (completed || !Files.isRegularFile(instance.resolve("loader-lifecycle-request.json")) || !ModelLoaderBase.awaitParsing(1)) return;
        completed = true;
        JsonObject report = new JsonObject();
        report.addProperty("timestamp", OffsetDateTime.now().toString());
        try {
            JsonObject request = org.mtr.libraries.com.google.gson.JsonParser.parseString(Files.readString(instance.resolve("loader-lifecycle-request.json"))).getAsJsonObject();
            report.add("request", request);
            JsonObject checks = new JsonObject(); report.add("checks", checks);
            audit(checks, request.has("faults") && request.get("faults").getAsBoolean()); report.addProperty("passed", true);
        } catch (Throwable error) {
            report.addProperty("passed", false); report.addProperty("error", error.toString());
            java.io.StringWriter trace = new java.io.StringWriter(); error.printStackTrace(new java.io.PrintWriter(trace));
            report.addProperty("stack", trace.toString());
        }
        try { Files.writeString(instance.resolve("loader-lifecycle-result.json"), report + "\n", StandardOpenOption.CREATE_NEW); }
        catch (Exception error) { throw new RuntimeException(error); }
        if (Boolean.getBoolean("mtr.memory.acceptance.exit")
                && (!Files.isRegularFile(instance.resolve("v6-compatibility-request.json"))
                || Files.isRegularFile(instance.resolve("v6-compatibility-result.json")))) Minecraft.getInstance().stop();
    }
    private static void check(JsonObject result, String key, boolean value) {
        if (!value) throw new AssertionError(key);
        result.addProperty(key, true);
    }
    private static ModelLoaderBase factory(ResourceProvider provider) throws Exception {
        var method = VehicleModel.class.getDeclaredMethod("getModelLoaderBase", String.class, String.class, ResourceProvider.class, boolean.class);
        method.setAccessible(true);
        return (ModelLoaderBase) method.invoke(null, "test:model.bbmodel", "test:texture.png", provider, false);
    }
    private static boolean loaded(ModelLoaderBase loader) throws Exception {
        Field field = ModelLoaderBase.class.getDeclaredField("modelLoaded"); field.setAccessible(true); return field.getBoolean(loader);
    }
    private static void audit(JsonObject checks, boolean faults) throws Exception {
        check(checks, "quiescent_before_probe", SharedBlockbenchCache.statistics().outstanding() == 0);
        var reads = new AtomicInteger(); var fail = new java.util.concurrent.atomic.AtomicBoolean();
        ResourceProvider provider = ignored -> {
            reads.incrementAndGet();
            if (fail.get()) throw new IllegalStateException("Injected resource failure");
            return "{\"meta\":{\"format_version\":\"4.10\"},\"elements\":[],\"outliner\":[],\"textures\":[]}";
        };
        SharedBlockbenchCache.beginReload();
        ModelLoaderBase first = factory(provider);
        check(checks, "factory_mixin_applied", first.getClass().getSimpleName().equals("SharedBlockbenchLoader"));
        check(checks, "accessor_mixin_applied", first instanceof ModelLoaderAccess);
        check(checks, "native_inline_publication", ModelLoaderBase.awaitParsing(10_000) && loaded(first));
        ModelLoaderBase second = factory(provider);
        check(checks, "path_hit_without_read", ModelLoaderBase.awaitParsing(10_000) && loaded(second) && reads.get() == 1);
        check(checks, "one_unique_parse", SharedBlockbenchCache.statistics().uniqueParses() == 1);
        SharedBlockbenchCache.beginReload(); fail.set(true);
        ModelLoaderBase failed = factory(provider);
        check(checks, "read_failure_unloaded", ModelLoaderBase.awaitParsing(10_000) && !loaded(failed));
        var failure = failed.getClass().getDeclaredMethod("failure"); failure.setAccessible(true);
        check(checks, "terminal_failure_recorded", failure.invoke(failed) != null && SharedBlockbenchCache.statistics().pending() == 0);
        fail.set(false);
        ModelLoaderBase retry = factory(provider);
        check(checks, "failed_path_retry", ModelLoaderBase.awaitParsing(10_000) && loaded(retry));
        SharedBlockbenchCache.finishRegistration();
        check(checks, "tickets_permits_and_keys_released", SharedBlockbenchCache.statistics().outstanding() == 0
                && SharedBlockbenchCache.statistics().paths() == 0 && ReadAdmission.GLOBAL.active() == 0);
        if (faults) auditFaults(checks);
    }
    private static void auditFaults(JsonObject checks) throws Exception {
        String valid = "{\"meta\":{\"format_version\":\"4.10\"},\"elements\":[],\"outliner\":[],\"textures\":[]}";
        String[] names = {"missing", "truncated", "wrong_root"};
        String[] inputs = {null, "{", "[]"};
        for (int index = 0; index < inputs.length; index++) {
            final String invalid = inputs[index];
            var repaired = new java.util.concurrent.atomic.AtomicBoolean();
            ResourceProvider provider = ignored -> repaired.get() ? valid : invalid;
            SharedBlockbenchCache.beginReload();
            ModelLoaderBase failed = factory(provider);
            var failure = failed.getClass().getDeclaredMethod("failure"); failure.setAccessible(true);
            check(checks, names[index] + "_terminal_failure", ModelLoaderBase.awaitParsing(10_000)
                    && !loaded(failed) && failure.invoke(failed) != null
                    && SharedBlockbenchCache.statistics().pending() == 0);
            repaired.set(true);
            ModelLoaderBase retry = factory(provider);
            check(checks, names[index] + "_same_path_retry", ModelLoaderBase.awaitParsing(10_000) && loaded(retry));
        }
        SharedBlockbenchCache.finishRegistration();
        check(checks, "fault_counts_settled", ModelLoaderBase.awaitParsing(10_000)
                && SharedBlockbenchCache.statistics().outstanding() == 0
                && SharedBlockbenchCache.statistics().pending() == 0 && ReadAdmission.GLOBAL.active() == 0);
    }
}
