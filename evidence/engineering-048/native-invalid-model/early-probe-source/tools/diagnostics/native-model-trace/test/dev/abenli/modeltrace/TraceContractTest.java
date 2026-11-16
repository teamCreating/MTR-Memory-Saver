package dev.abenli.modeltrace;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;

final class TraceContractTest {
    private static ClassNode read(String path) throws Exception {
        try (var input = TraceContractTest.class.getResourceAsStream(path)) {
            assertNotNull(input); var node = new ClassNode(); new ClassReader(input).accept(node, 0); return node;
        }
    }
    @Test void exactLoggerInjectionHasOneTargetAndOneReturn() throws Exception {
        var method = read("/org/mtr/resource/VehicleModel.class").methods.stream().filter(value -> value.name.equals("getModelLoaderBase")).findFirst().orElseThrow();
        assertEquals("(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;", method.desc);
        int loggerCalls = 0, returns = 0;
        for (var instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode invocation && invocation.owner.equals("org/apache/logging/log4j/Logger")
                    && invocation.name.equals("error") && invocation.desc.equals("(Ljava/lang/String;Ljava/lang/Object;)V")) loggerCalls++;
            if (instruction.getOpcode() == Opcodes.ARETURN) returns++;
        }
        assertEquals(1, loggerCalls); assertEquals(1, returns);
    }
    @Test void exactTargetChangesAreRejected() throws Exception {
        var value = TargetGuard.metadata();
        String minecraft = value.get("minecraft").getAsString(), neoForge = value.get("neoForge").getAsString(), sha = value.get("mtrSha256").getAsString();
        int java = value.get("java").getAsInt();
        assertDoesNotThrow(() -> TargetGuard.verify(value, minecraft, java, neoForge, sha));
        assertThrows(IllegalStateException.class, () -> TargetGuard.verify(value, "wrong", java, neoForge, sha));
        assertThrows(IllegalStateException.class, () -> TargetGuard.verify(value, minecraft, java + 1, neoForge, sha));
        assertThrows(IllegalStateException.class, () -> TargetGuard.verify(value, minecraft, java, "wrong", sha));
        assertThrows(IllegalStateException.class, () -> TargetGuard.verify(value, minecraft, java, neoForge, "wrong"));
    }
    @Test void observerCallsNeitherLazyFactoriesNorProductApis() throws Exception {
        var node = read("/dev/abenli/modeltrace/TraceRecorder.class");
        for (var method : node.methods) for (var instruction : method.instructions) if (instruction instanceof MethodInsnNode invocation) {
            assertFalse(invocation.owner.startsWith("site/benli06/"));
            assertNotEquals("getModelLoaderBase", invocation.name); assertNotEquals("getOptimizedModel", invocation.name);
            assertNotEquals("awaitParsing", invocation.name); assertNotEquals("getCachedVehicleResource", invocation.name);
        }
    }
}
