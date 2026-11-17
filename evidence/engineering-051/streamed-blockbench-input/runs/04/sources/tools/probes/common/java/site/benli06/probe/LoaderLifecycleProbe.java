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
import site.benli06.CompressedResourceTextCache;
import site.benli06.mixin.ModelLoaderAccess;

/** Actual client-side Mixin smoke check; empty fixtures do not certify rendered geometry/GPU. */
@Mod(value = "mtr_memory_loader_probe", dist = Dist.CLIENT)
public final class LoaderLifecycleProbe {
    private static final ResourceProvider NATIVE_RESOURCE_PROVIDER = NativeResourceReadFixture::readActual;
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
            boolean faults = request.has("faults") && request.get("faults").getAsBoolean();
            JsonObject strictChecks = new JsonObject(), strictObservations = new JsonObject();
            if (faults) { report.add("strict_resource_checks", strictChecks); report.add("strict_resource_observations", strictObservations); }
            audit(checks, faults, strictChecks, strictObservations); report.addProperty("passed", true);
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
        return factory("test:model.bbmodel", provider);
    }
    private static ModelLoaderBase factory(String model, ResourceProvider provider) throws Exception {
        var method = VehicleModel.class.getDeclaredMethod("getModelLoaderBase", String.class, String.class, ResourceProvider.class, boolean.class);
        method.setAccessible(true);
        return (ModelLoaderBase) method.invoke(null, model, "test:texture.png", provider, false);
    }
    private static boolean loaded(ModelLoaderBase loader) throws Exception {
        Field field = ModelLoaderBase.class.getDeclaredField("modelLoaded"); field.setAccessible(true); return field.getBoolean(loader);
    }
    private static void audit(JsonObject checks, boolean faults, JsonObject strictChecks, JsonObject strictObservations) throws Exception {
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
        check(checks, "tickets_permits_and_keys_released", settled()
                && SharedBlockbenchCache.statistics().paths() == 0 && ReadAdmission.GLOBAL.active() == 0);
        if (faults) auditFaults(checks, strictChecks, strictObservations);
    }
    private static void auditFaults(JsonObject checks, JsonObject strictChecks, JsonObject strictObservations) throws Exception {
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
        check(checks, "oversized_resource_terminal_failure", auditStrictResources(strictChecks, strictObservations, valid));
        auditNativeRetirement(checks, valid);
        SharedBlockbenchCache.finishRegistration();
        check(checks, "fault_counts_settled", settled()
                && SharedBlockbenchCache.statistics().pending() == 0 && ReadAdmission.GLOBAL.active() == 0);
    }
    private static boolean auditStrictResources(JsonObject checks, JsonObject observations, String valid) throws Exception {
        long limit = ReadAdmission.GLOBAL.maxCodeUnits();
        observations.addProperty("decoded_limit", limit);
        observations.add("workspace_before", workspaceObservation());
        boolean oversizedPassed = false;
        for (var mode : new NativeResourceReadFixture.Mode[]{NativeResourceReadFixture.Mode.OPEN_FAILURE,
                NativeResourceReadFixture.Mode.READ_FAILURE, NativeResourceReadFixture.Mode.CLOSE_FAILURE,
                NativeResourceReadFixture.Mode.OVERSIZED}) {
            String name = mode.name().toLowerCase(java.util.Locale.ROOT);
            JsonObject detail = new JsonObject(); observations.add(name, detail);
            CompressedResourceTextCache.clear(); SharedBlockbenchCache.beginReload();
            try (var fixture = NativeResourceReadFixture.register(mode, valid)) {
                ModelLoaderBase failed = factory(fixture.id.toString(), NATIVE_RESOURCE_PROVIDER);
                boolean terminal = ModelLoaderBase.awaitParsing(mode == NativeResourceReadFixture.Mode.OVERSIZED ? 120_000 : 10_000) && settled();
                Throwable error = failure(failed);
                detail.add("failed_read", fixture.observations());
                detail.addProperty("failure", String.valueOf(error));
                detail.add("failed_workspace", workspaceObservation());
                check(checks, name + "_actual_native_resource_open", fixture.lookups() == 1 && fixture.opens() == 1
                        && fixture.closes() == (mode == NativeResourceReadFixture.Mode.OPEN_FAILURE ? 0 : 1));
                boolean expectedFailure = mode == NativeResourceReadFixture.Mode.OVERSIZED
                        ? error instanceof IllegalStateException && fixture.bytesRead() > limit
                        : hasIoFailure(error, mode);
                check(checks, name + "_terminal_failure_without_empty_cache", terminal && !loaded(failed) && expectedFailure
                        && CompressedResourceTextCache.statistics()[0] == 0 && CompressedResourceTextCache.activity()[6] == 0);
                fixture.correct();
                ModelLoaderBase retry = factory(fixture.id.toString(), NATIVE_RESOURCE_PROVIDER);
                check(checks, name + "_same_key_correction_retry", ModelLoaderBase.awaitParsing(10_000) && loaded(retry) && settled()
                        && valid.equals(NativeResourceReadFixture.readActual(fixture.id)) && fixture.lookups() == 2 && fixture.opens() == 2);
                detail.add("corrected_read", fixture.observations());
                if (mode == NativeResourceReadFixture.Mode.OVERSIZED) oversizedPassed = true;
            }
        }
        CompressedResourceTextCache.clear();
        try (var empty = NativeResourceReadFixture.register(NativeResourceReadFixture.Mode.EMPTY, valid)) {
            check(checks, "legal_empty_text_is_success_and_cache_hit", NativeResourceReadFixture.readActual(empty.id).isEmpty()
                    && NativeResourceReadFixture.readActual(empty.id).isEmpty() && empty.lookups() == 1 && empty.opens() == 1
                    && empty.closes() == 1 && CompressedResourceTextCache.statistics()[0] == 1 && settled());
            observations.add("legal_empty", empty.observations());
        }
        CompressedResourceTextCache.clear();
        try (var malformed = NativeResourceReadFixture.register(NativeResourceReadFixture.Mode.MALFORMED_UTF8, valid)) {
            String expected = NativeResourceReadFixture.malformedReplacement();
            check(checks, "malformed_utf8_keeps_native_replacement_and_cache_hit", expected.equals(NativeResourceReadFixture.readActual(malformed.id))
                    && expected.equals(NativeResourceReadFixture.readActual(malformed.id)) && malformed.lookups() == 1
                    && malformed.opens() == 1 && malformed.closes() == 1 && settled());
            observations.add("malformed_utf8", malformed.observations());
        }
        CompressedResourceTextCache.clear();
        try (var missing = NativeResourceReadFixture.register(NativeResourceReadFixture.Mode.MISSING, valid)) {
            check(checks, "missing_optional_keeps_native_empty_cache_semantics", NativeResourceReadFixture.readActual(missing.id).isEmpty()
                    && NativeResourceReadFixture.readActual(missing.id).isEmpty() && missing.lookups() == 1 && missing.opens() == 0);
            missing.correct();
            check(checks, "missing_correction_requires_native_cache_retirement", NativeResourceReadFixture.readActual(missing.id).isEmpty()
                    && missing.opens() == 0);
            CompressedResourceTextCache.clear();
            check(checks, "missing_retry_after_cache_retirement", valid.equals(NativeResourceReadFixture.readActual(missing.id))
                    && missing.lookups() == 2 && missing.opens() == 1 && missing.closes() == 1 && settled());
            observations.add("missing", missing.observations());
        }
        SharedBlockbenchCache.finishRegistration(); CompressedResourceTextCache.clear();
        check(checks, "strict_fixture_and_workspace_cleanup", NativeResourceReadFixture.active() == 0 && settled()
                && CompressedResourceTextCache.statistics()[0] == 0 && CompressedResourceTextCache.activity()[6] == 0);
        observations.add("workspace_after", workspaceObservation());
        return oversizedPassed;
    }
    private static Throwable failure(ModelLoaderBase loader) throws Exception {
        var method = loader.getClass().getDeclaredMethod("failure"); method.setAccessible(true);
        return (Throwable) method.invoke(loader);
    }
    private static boolean hasIoFailure(Throwable error, NativeResourceReadFixture.Mode phase) {
        for (Throwable current = error; current != null; current = current.getCause())
            if (current instanceof NativeResourceReadFixture.FaultIOException failure && failure.phase == phase) return true;
        return false;
    }
    private static JsonObject workspaceObservation() {
        long[] stats = ReadAdmission.GLOBAL.workspaceStatistics();
        JsonObject value = new JsonObject(); value.addProperty("budget_bytes", stats[0]); value.addProperty("used_bytes", stats[1]);
        value.addProperty("peak_bytes", stats[2]); value.addProperty("waiting_requests", stats[3]); return value;
    }
    private static void auditNativeRetirement(JsonObject checks, String valid) throws Exception {
        SharedBlockbenchCache.beginReload();
        ResourceProvider provider = ignored -> valid;
        ModelLoaderBase old;
        ModelLoaderBase fresh;
        try (var gate = NativeParserPause.arm()) {
            old = factory(provider);
            check(checks, "actual_native_parser_paused", gate.awaitEntered() && !ModelLoaderBase.awaitParsing(1));
            SharedBlockbenchCache.beginReload();
            var failure = old.getClass().getDeclaredMethod("failure"); failure.setAccessible(true);
            check(checks, "canceled_native_facade_terminal", !loaded(old) && failure.invoke(old) instanceof java.util.concurrent.CancellationException);
            check(checks, "running_native_owner_keeps_ticket_and_permit", !ModelLoaderBase.awaitParsing(1)
                    && SharedBlockbenchCache.statistics().outstanding() == 1 && ReadAdmission.GLOBAL.active() == 1);
            fresh = factory(provider);
            long started = System.nanoTime();
            while (!loaded(fresh) && System.nanoTime() - started < java.util.concurrent.TimeUnit.SECONDS.toNanos(5)) Thread.sleep(2);
            check(checks, "replacement_publishes_while_old_native_parse_is_blocked", loaded(fresh));
        }
        check(checks, "native_retirement_cleanup", settled());
        check(checks, "late_native_publication_cannot_repopulate_retired_facade", !loaded(old) && loaded(fresh));
    }
    private static boolean settled() throws InterruptedException {
        long started = System.nanoTime();
        do {
            long[] workspace = ReadAdmission.GLOBAL.workspaceStatistics();
            if (ModelLoaderBase.awaitParsing(1) && SharedBlockbenchCache.statistics().outstanding() == 0
                    && ReadAdmission.GLOBAL.active() == 0 && workspace[1] == 0 && workspace[3] == 0) return true;
            Thread.sleep(2);
        } while (System.nanoTime() - started < java.util.concurrent.TimeUnit.SECONDS.toNanos(10));
        return false;
    }
}
