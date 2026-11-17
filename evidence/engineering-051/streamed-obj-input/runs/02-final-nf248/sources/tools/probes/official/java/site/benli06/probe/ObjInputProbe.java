package site.benli06.probe;

import java.lang.reflect.Field;
import java.util.concurrent.atomic.AtomicInteger;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.mtr.libraries.com.google.gson.JsonObject;
import site.benli06.NativeResourceSnapshots;
import site.benli06.ReadAdmission;
import site.benli06.StreamedObjCache;
import site.benli06.mixin.ModelLoaderAccess;

/** Actual factory, resource, native-mesh invoker and failure/retry checks in an isolated client. */
public final class ObjInputProbe {
    private static final String TRIANGLE = "g body\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nvn 0 0 1\nf 1/1/1 2/2/1 3/3/1\n";
    private static void check(JsonObject checks, String key, boolean success) {
        if (!success) throw new AssertionError(key);
        checks.addProperty(key, true);
    }
    private static ModelLoaderBase factory(String model, ResourceProvider provider, boolean flip) throws Exception {
        var method = VehicleModel.class.getDeclaredMethod("getModelLoaderBase", String.class, String.class, ResourceProvider.class, boolean.class);
        method.setAccessible(true);
        return (ModelLoaderBase) method.invoke(null, model, "test:texture.png", provider, flip);
    }
    private static boolean loaded(ModelLoaderBase loader) throws Exception {
        Field flag = ModelLoaderBase.class.getDeclaredField("modelLoaded"); flag.setAccessible(true); return flag.getBoolean(loader);
    }
    private static Throwable failure(ModelLoaderBase loader) throws Exception {
        var method = loader.getClass().getDeclaredMethod("failure"); method.setAccessible(true); return (Throwable) method.invoke(loader);
    }
    private static boolean settled() {
        var stats = StreamedObjCache.statistics();
        return stats.pending() == 0 && stats.outstanding() == 0 && stats.queued() == 0 && ReadAdmission.GLOBAL.active() == 0;
    }
    private static boolean await(long milliseconds) throws InterruptedException {
        long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(milliseconds);
        do {
            if (ModelLoaderBase.awaitParsing(1) && settled()) return true;
            Thread.sleep(1);
        } while (System.nanoTime() < deadline);
        return false;
    }
    public static void audit(JsonObject checks) throws Exception {
        check(checks, "obj_quiescent_before", await(10000));
        var stringReads = new AtomicInteger();
        ResourceProvider provider = NativeResourceSnapshots.wrap(id -> {
            stringReads.incrementAndGet(); return NativeResourceReadFixture.readActual(id);
        });
        StreamedObjCache.beginReload();
        try (var material = NativeResourceReadFixture.register(NativeResourceReadFixture.Mode.CORRECTED, "newmtl paint\nKd .2 .4 .6\n", "mtl")) {
            String materialName = material.id.getPath().substring(material.id.getPath().lastIndexOf('/') + 1);
            String text = "mtllib " + materialName + "\nusemtl paint\n" + TRIANGLE;
            try (var fixture = NativeResourceReadFixture.register(NativeResourceReadFixture.Mode.CORRECTED, text, "obj")) {
                ModelLoaderBase first = factory(fixture.id.toString(), provider, false);
                check(checks, "obj_factory_mixin", first.getClass().getSimpleName().equals("SharedObjLoader"));
                check(checks, "obj_native_mesh_published", await(10000) && loaded(first)
                        && ((ModelLoaderAccess) first).meshes().containsKey("body"));
                check(checks, "obj_and_mtl_streamed", stringReads.get() == 0 && fixture.opens() == 1 && material.opens() == 1);
                check(checks, "obj_and_mtl_inputs_closed", fixture.closes() == 1 && material.closes() == 1);
                ModelLoaderBase second = factory(fixture.id.toString(), provider, false);
                check(checks, "obj_path_hit_without_read", await(10000) && loaded(second) && fixture.opens() == 1 && material.opens() == 1);
                ModelLoaderBase flipped = factory(fixture.id.toString(), provider, true);
                check(checks, "obj_flip_variant_separate", await(10000) && loaded(flipped) && StreamedObjCache.statistics().uniqueParses() == 2);
                StreamedObjCache.beginReload();
                ModelLoaderBase refreshed = factory(fixture.id.toString(), provider, false);
                check(checks, "obj_epoch_reads_again", await(10000) && loaded(refreshed) && fixture.opens() == 3 && material.opens() == 3);
            }
        }
        StreamedObjCache.finishRegistration();
        check(checks, "obj_keys_and_tickets_released", settled() && StreamedObjCache.statistics().paths() == 0 && StreamedObjCache.statistics().contents() == 0);
        for (var mode : new NativeResourceReadFixture.Mode[] {NativeResourceReadFixture.Mode.OPEN_FAILURE,
                NativeResourceReadFixture.Mode.READ_FAILURE, NativeResourceReadFixture.Mode.CLOSE_FAILURE,
                NativeResourceReadFixture.Mode.OVERSIZED, NativeResourceReadFixture.Mode.MALFORMED_OBJ}) {
            StreamedObjCache.beginReload();
            try (var fixture = NativeResourceReadFixture.register(mode, TRIANGLE, "obj")) {
                ModelLoaderBase failed = factory(fixture.id.toString(), provider, false);
                check(checks, "obj_" + mode.name().toLowerCase(java.util.Locale.ROOT) + "_unloaded",
                        await(120000) && !loaded(failed) && failure(failed) != null);
                fixture.correct();
                ModelLoaderBase retry = factory(fixture.id.toString(), provider, false);
                check(checks, "obj_" + mode.name().toLowerCase(java.util.Locale.ROOT) + "_same_key_retry",
                        await(10000) && loaded(retry));
            }
            StreamedObjCache.finishRegistration();
        }
        check(checks, "obj_no_string_fallback", stringReads.get() == 0);
        var unknownReads = new AtomicInteger();
        ResourceProvider unknown = id -> { unknownReads.incrementAndGet(); return TRIANGLE; };
        var ordinary = factory("test:unknown.obj", unknown, false);
        check(checks, "obj_unknown_provider_native_contract", await(10000) && loaded(ordinary)
                && ordinary.getClass().getSimpleName().equals("ObjModelLoader") && unknownReads.get() == 1);
        StreamedObjCache.beginReload();
        var declinedReads = new AtomicInteger();
        var declined = new site.benli06.SnapshotResourceProvider(id -> { declinedReads.incrementAndGet(); return TRIANGLE; }, id -> java.util.Optional.empty());
        var fallback = factory("test:declined.obj", declined, false);
        check(checks, "obj_declined_capability_string_contract", await(10000) && loaded(fallback) && declinedReads.get() == 1);
        StreamedObjCache.finishRegistration();
        retirement(checks);
        long[] workspace = ReadAdmission.GLOBAL.workspaceStatistics();
        check(checks, "obj_final_ownership_balanced", settled() && NativeResourceReadFixture.active() == 0
                && workspace[1] == 0 && workspace[3] == 0);
    }
    private static void retirement(JsonObject checks) throws Exception {
        StreamedObjCache.beginReload();
        var entered = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        var owned = new java.util.concurrent.atomic.AtomicReference<site.benli06.ResourceTextSnapshot>();
        var provider = new site.benli06.SnapshotResourceProvider(id -> { throw new AssertionError("Unexpected fallback"); }, id -> {
            try {
                var snapshot = site.benli06.ResourceTextSnapshot.open(
                        () -> new java.io.ByteArrayInputStream(TRIANGLE.getBytes(java.nio.charset.StandardCharsets.UTF_8)),
                        java.nio.charset.StandardCharsets.UTF_8, ReadAdmission.GLOBAL);
                owned.set(snapshot); entered.countDown();
                long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(10);
                while (release.getCount() != 0 && System.nanoTime() < deadline) {
                    try { release.await(10, java.util.concurrent.TimeUnit.MILLISECONDS); }
                    catch (InterruptedException ignored) { /* Exercise a real late owner exit. */ }
                }
                return java.util.Optional.of(snapshot);
            } catch (java.io.IOException error) { throw new java.io.UncheckedIOException(error); }
        });
        try {
            var pending = factory("test:retired.obj", provider, false);
            check(checks, "obj_retirement_owner_entered", entered.await(5, java.util.concurrent.TimeUnit.SECONDS));
            StreamedObjCache.beginReload();
            check(checks, "obj_retirement_keeps_running_ticket", StreamedObjCache.statistics().outstanding() == 1
                    && ReadAdmission.GLOBAL.active() == 1 && !ModelLoaderBase.awaitParsing(1));
            release.countDown();
            check(checks, "obj_retirement_no_publication", await(10000) && !loaded(pending)
                    && failure(pending) instanceof java.util.concurrent.CancellationException);
            boolean closed = false;
            try (var reader = owned.get().reader()) { }
            catch (java.io.IOException expected) { closed = true; }
            check(checks, "obj_retirement_snapshot_closed", closed);
        } finally { release.countDown(); }
        StreamedObjCache.finishRegistration();
    }
}
