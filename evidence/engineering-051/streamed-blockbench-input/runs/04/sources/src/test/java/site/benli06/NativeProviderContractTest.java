package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.util.HashSet;
import java.util.Set;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Handle;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.InvokeDynamicInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

/** Proves that only the native default provider is passed at the five optional-capability hooks. */
class NativeProviderContractTest {
    @Test void everyHookProviderIsExactlyTheNativeReadResourceMethodReference() throws Exception {
        try (var metadata = getClass().getClassLoader().getResourceAsStream("mtr-memory-target.json")) {
            assertNotNull(metadata);
            var target = org.mtr.libraries.com.google.gson.JsonParser.parseReader(new InputStreamReader(metadata, StandardCharsets.UTF_8)).getAsJsonObject();
            Assumptions.assumeTrue(target.get("variant").getAsString().equals("official"));
        }
        try (var input = getClass().getClassLoader().getResourceAsStream("org/mtr/client/CustomResourceLoader.class")) {
            assertNotNull(input);
            ClassNode type = new ClassNode(); new ClassReader(input).accept(type, 0);
            Set<String> actual = new HashSet<>(); int providers = 0;
            for (var method : type.methods) {
                for (var instruction : method.instructions) {
                    if (!(instruction instanceof InvokeDynamicInsnNode dynamic)
                            || !dynamic.desc.equals("()Lorg/mtr/resource/ResourceProvider;")) continue;
                    providers++;
                    assertEquals("java/lang/invoke/LambdaMetafactory", dynamic.bsm.getOwner());
                    assertEquals("metafactory", dynamic.bsm.getName());
                    Handle implementation = (Handle) dynamic.bsmArgs[1];
                    assertEquals(Opcodes.H_INVOKESTATIC, implementation.getTag());
                    assertEquals("org/mtr/client/CustomResourceLoader", implementation.getOwner());
                    assertEquals("readResource", implementation.getName());
                    assertEquals("(Lnet/minecraft/resources/ResourceLocation;)Ljava/lang/String;", implementation.getDesc());
                    AbstractInsnNode next = instruction.getNext();
                    while (next != null && next.getOpcode() < 0) next = next.getNext();
                    assertInstanceOf(MethodInsnNode.class, next);
                    MethodInsnNode call = (MethodInsnNode) next;
                    assertTrue(actual.add(method.name + "|" + call.owner + "|" + call.name + call.desc));
                }
            }
            assertEquals(5, providers);
            String converter = "org/mtr/legacy/resource/CustomResourcesConverter|";
            String convert = "convert(Lorg/mtr/libraries/com/google/gson/JsonObject;Lorg/mtr/resource/ResourceProvider;)Lorg/mtr/resource/CustomResources;";
            assertEquals(Set.of(
                    "reload|org/mtr/resource/RailResource|<init>(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;)V",
                    "reload|" + converter + "convertRails(Ljava/util/function/Consumer;Lorg/mtr/resource/ResourceProvider;)V",
                    "reload|" + converter + "convertObjects(Ljava/util/function/Consumer;Lorg/mtr/resource/ResourceProvider;)V",
                    "lambda$reload$8|" + converter + convert,
                    "lambda$reload$10|" + converter + convert), actual);
        }
    }
}
