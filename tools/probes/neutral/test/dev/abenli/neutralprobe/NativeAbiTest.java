package dev.abenli.neutralprobe;

import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;

/** Verifies fields/targets in the audited dependency without launching Minecraft. */
final class NativeAbiTest {
    private static ClassNode read(String resource) throws IOException {
        try (var input = NativeAbiTest.class.getResourceAsStream(resource)) {
            assertNotNull(input, resource);
            var node = new ClassNode();
            new ClassReader(input).accept(node, 0);
            return node;
        }
    }
    @Test void readOnlyAccessorTargetsMatchOfficialFields() throws Exception {
        var pending = read("/org/mtr/model/ModelLoaderBase.class").fields.stream()
                .filter(field -> field.name.equals("PENDING_PARSE_COUNT")).findFirst().orElseThrow();
        assertEquals("Ljava/util/concurrent/atomic/AtomicInteger;", pending.desc);
        assertTrue((pending.access & Opcodes.ACC_STATIC) != 0);
        var cache = read("/org/mtr/resource/VehicleResource.class").fields.stream()
                .filter(field -> field.name.equals("vehicleResourceCacheByCarNumberAndTotalCars")).findFirst().orElseThrow();
        assertEquals("Lorg/mtr/libraries/it/unimi/dsi/fastutil/ints/Int2ObjectAVLTreeMap;", cache.desc);
        var instance = read("/org/mtr/client/MinecraftClientData.class").fields.stream()
                .filter(field -> field.name.equals("instance")).findFirst().orElseThrow();
        assertEquals("Lorg/mtr/client/MinecraftClientData;", instance.desc);
        assertTrue((instance.access & Opcodes.ACC_STATIC) != 0);
        var progress = read("/org/mtr/core/generated/data/VehicleSchema.class").fields.stream()
                .filter(field -> field.name.equals("railProgress")).findFirst().orElseThrow();
        assertEquals("D", progress.desc);
    }
    @Test void nativeReloadHasTheRequiredStaticVoidEntryPoint() throws Exception {
        var method = read("/org/mtr/client/CustomResourceLoader.class").methods.stream()
                .filter(candidate -> candidate.name.equals("reload") && candidate.desc.equals("()V")).findFirst().orElseThrow();
        assertTrue((method.access & Opcodes.ACC_STATIC) != 0);
        assertTrue(method.instructions.size() > 0);
        var config = ObservationSchema.resource("/mtr-native-observer.mixins.json");
        assertTrue(config.get("required").getAsBoolean());
        assertEquals(1, config.getAsJsonObject("injectors").get("defaultRequire").getAsInt());
    }
    @Test void observerNeverInvokesNativeLazyFactoriesOrCompanionApis() throws Exception {
        for (String name : new String[]{"NativeScene", "NativeRegistry", "NativeObserver", "NativeModelDiagnostics", "mixin/NativeInvalidModelMixin"}) {
            var node = read("/dev/abenli/neutralprobe/" + name + ".class");
            for (var method : node.methods) {
                for (var instruction : method.instructions) {
                    if (instruction instanceof MethodInsnNode invocation) {
                        assertFalse(invocation.owner.startsWith("site/benli06/"), invocation.owner);
                        assertNotEquals("getCachedVehicleResource", invocation.name);
                        assertNotEquals("awaitParsing", invocation.name);
                        assertNotEquals("getOptimizedModel", invocation.name);
                        if (invocation.owner.startsWith("org/spongepowered/asm/mixin/injection/callback/")) {
                            assertNotEquals("cancel", invocation.name);
                            assertNotEquals("setReturnValue", invocation.name);
                        }
                        if (invocation.owner.equals("org/mtr/client/MinecraftClientData"))
                            assertNotEquals("getInstance", invocation.name);
                    }
                }
            }
        }
    }
    @Test void invalidModelDiagnosticMatchesTheSingleNativeLogAndFinalReturn() throws Exception {
        var method = read("/org/mtr/resource/VehicleModel.class").methods.stream()
                .filter(candidate -> candidate.name.equals("getModelLoaderBase")).findFirst().orElseThrow();
        assertEquals("(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;", method.desc);
        assertTrue((method.access & Opcodes.ACC_STATIC) != 0);
        int errors = 0, returns = 0;
        for (var instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode invocation && invocation.owner.equals("org/apache/logging/log4j/Logger")
                    && invocation.name.equals("error") && invocation.desc.equals("(Ljava/lang/String;Ljava/lang/Object;)V")) errors++;
            if (instruction.getOpcode() == Opcodes.ARETURN) returns++;
        }
        assertEquals(1, errors); assertEquals(1, returns);
        var metadata = ObservationSchema.resource("/mtr-native-observer-target.json");
        assertEquals(1, metadata.get("diagnostics_schema").getAsInt());
        assertTrue(metadata.get("diagnostics_path").getAsString().endsWith(".jsonl"));
        assertTrue(ObservationSchema.resource("/capabilities.json").getAsJsonObject("capabilities")
                .get("native_model_diagnostics").getAsBoolean());
    }
    @Test void nativeWindowAndMouseFocusQueriesExistWithoutInputMutation() throws Exception {
        var minecraft = read("/net/minecraft/client/Minecraft.class");
        assertTrue(minecraft.methods.stream().anyMatch(method -> method.name.equals("isWindowActive") && method.desc.equals("()Z")
                && (method.access & Opcodes.ACC_PUBLIC) != 0));
        assertTrue(minecraft.fields.stream().anyMatch(field -> field.name.equals("mouseHandler")
                && field.desc.equals("Lnet/minecraft/client/MouseHandler;") && (field.access & Opcodes.ACC_PUBLIC) != 0));
        assertTrue(read("/net/minecraft/client/MouseHandler.class").methods.stream().anyMatch(method ->
                method.name.equals("isMouseGrabbed") && method.desc.equals("()Z") && (method.access & Opcodes.ACC_PUBLIC) != 0));
    }
}
