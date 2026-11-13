package site.benli06.audit;

import java.awt.Color;
import java.lang.reflect.*;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import com.mojang.blaze3d.vertex.VertexConsumer;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.phys.AABB;
import org.mtr.model.*;
import org.mtr.resource.RenderStage;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;
import site.benli06.*;

/** Compares packed data and emitted values with unmodified target-release methods. */
public final class PackedMeshAudit {
    // The audit supports both released Color and v6 integer-color ABIs; production
    // code remains compiled against one explicitly fingerprinted target.
    private static final Method COLOR;
    private static final Constructor<?> VERTEX;
    static {
        try {
            COLOR = StoredVertexData.class.getMethod("color");
            VERTEX = StoredVertexData.class.getConstructor(float.class, float.class, float.class,
                    COLOR.getReturnType(), float.class, float.class, float.class, float.class, float.class);
        } catch (ReflectiveOperationException error) { throw new ExceptionInInitializerError(error); }
    }
    private static int argb(StoredVertexData vertex) {
        try {
            Object color = COLOR.invoke(vertex);
            return color instanceof Color value ? value.getRGB() : (Integer) color;
        } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
    }
    static StoredVertexData createVertex(float x, float y, float z, Color color,
                                                  float u, float v, float nx, float ny, float nz) {
        try {
            Object value = COLOR.getReturnType() == int.class ? Integer.valueOf(color.getRGB()) : color;
            return (StoredVertexData) VERTEX.newInstance(x, y, z, value, u, v, nx, ny, nz);
        } catch (ReflectiveOperationException error) { throw new AssertionError(error); }
    }
    private static final class Output {
        final MessageDigest digest;
        final ByteBuffer bytes = ByteBuffer.allocate(44);
        int count;
        final VertexConsumer consumer;
        Output(boolean transformed) throws Exception {
            digest = MessageDigest.getInstance("SHA-256");
            consumer = (VertexConsumer) Proxy.newProxyInstance(VertexConsumer.class.getClassLoader(),
                    new Class<?>[]{VertexConsumer.class}, (proxy, method, args) -> {
                        if (!method.getName().equals("addVertex") || args.length != 11)
                            throw new AssertionError("Unexpected emit call: " + method);
                        bytes.clear();
                        for (int i = 0; i < args.length; i++) {
                            Object value = args[i];
                            // Only arithmetic-modified fields have unspecified NaN payloads.
                            if (value instanceof Float f) bytes.putInt(transformed &&
                                    (i <= 2 || i == 8 || i == 10) && Float.isNaN(f)
                                    ? Float.floatToIntBits(f) : Float.floatToRawIntBits(f));
                            else bytes.putInt((Integer) value);
                        }
                        digest.update(bytes.array()); count++;
                        return null;
                    });
        }
        String hash() { return HexFormat.of().formatHex(digest.digest()); }
    }

    private static int comparisons;
    private static long checkedVertices, arithmeticNaNPayloadVariations;
    private static void compare(ObjectArrayList<StoredVertexData> expected, PackedVertices packed) throws Exception {
        compare(expected, packed, false);
    }
    private static void compare(ObjectArrayList<StoredVertexData> expected, PackedVertices packed, boolean transformed) throws Exception {
        if (expected.size() != packed.size()) throw new AssertionError("Vertex count differs");
        int[] index = {0};
        packed.emit((x, y, z, color, u, v, nx, ny, nz) -> {
            StoredVertexData e = expected.get(index[0]++);
            if (color != argb(e)) throw new AssertionError("ARGB differs");
            float[] a = {x,y,z,u,v,nx,ny,nz}, b = {e.x(),e.y(),e.z(),e.u(),e.v(),e.normalX(),e.normalY(),e.normalZ()};
            for (int i = 0; i < a.length; i++) if (Float.floatToRawIntBits(a[i]) != Float.floatToRawIntBits(b[i])) {
                if (transformed && (i <= 2 || i == 5 || i == 7) && Float.isNaN(a[i]) && Float.isNaN(b[i]))
                    arithmeticNaNPayloadVariations++;
                else throw new AssertionError("Vertex " + (index[0]-1) + " field " + i + ": "
                        + Integer.toHexString(Float.floatToRawIntBits(a[i])) + " versus " + Integer.toHexString(Float.floatToRawIntBits(b[i])));
            }
        });
        checkedVertices += index[0];
        Output actual = new Output(transformed); Output reference = new Output(transformed);
        StoredVertexData.apply(expected, reference.consumer);
        PackedVertexEmitter.emit(packed, actual.consumer);
        if (actual.count != reference.count || actual.count != packed.size() || !actual.hash().equals(reference.hash())) {
            throw new AssertionError("Vertex emission mismatch");
        }
        comparisons++;
    }

    @SuppressWarnings("unchecked")
    static Map<RenderStage, Map<ResourceLocation, ObjectArrayList<StoredVertexData>>> groups(NewOptimizedModelGroup group) throws Exception {
        Field field = NewOptimizedModelGroup.class.getDeclaredField("storedVertexConsumersForRenderStageAndTexture");
        field.setAccessible(true);
        return (Map<RenderStage, Map<ResourceLocation, ObjectArrayList<StoredVertexData>>>) field.get(group);
    }

    static void compareGroup(NewOptimizedModelGroup reference, PackedModelGroupStore<ResourceLocation> candidate) throws Exception {
        var expected = groups(reference);
        if (!expected.keySet().equals(candidate.groups().keySet())) throw new AssertionError("Stage keys differ");
        for (var stage : expected.entrySet()) {
            var textures = candidate.groups().get(stage.getKey());
            if (!stage.getValue().keySet().equals(textures.keySet())) throw new AssertionError("Texture keys differ");
            for (var texture : stage.getValue().entrySet()) compare(texture.getValue(), textures.get(texture.getKey()));
        }
    }

    private static void add(NewOptimizedModelGroup reference, PackedModelGroupStore<ResourceLocation> candidate,
                            ObjectArrayList<AABB> candidateBoxes, RenderStage stage, ResourceLocation texture,
                            ObjectArrayList<StoredVertexData> vertices, ObjectArrayList<AABB> boxes) throws Exception {
        reference.add(stage, texture, list -> list.addAll(vertices), boxes);
        PackedModelGroupOperations.add(candidate, candidateBoxes, stage, texture, list -> list.addAll(vertices), boxes);
        if (!reference.boxes.equals(candidateBoxes)) throw new AssertionError("Interaction boxes differ");
        compareGroup(reference, candidate);
    }

    public static void main(String[] args) throws Exception {
        Random random = new Random(1793616000L);
        ObjectArrayList<StoredVertexData> vertices = new ObjectArrayList<>();
        float[] edge = {0, -0.0F, Float.MIN_VALUE, -Float.MIN_VALUE, Float.POSITIVE_INFINITY,
                Float.NEGATIVE_INFINITY, Float.intBitsToFloat(0x7fc00001), Float.intBitsToFloat(0x7f800001)};
        for (int i = 0; i < 100000; i++) vertices.add(createVertex(
                i < edge.length ? edge[i] : Float.intBitsToFloat(random.nextInt()),
                Float.intBitsToFloat(random.nextInt()), Float.intBitsToFloat(random.nextInt()),
                new Color(random.nextInt(), true), Float.intBitsToFloat(random.nextInt()),
                Float.intBitsToFloat(random.nextInt()), Float.intBitsToFloat(random.nextInt()),
                Float.intBitsToFloat(random.nextInt()), Float.intBitsToFloat(random.nextInt())));
        PackedVertices packed = new PackedVertices(); packed.append(vertices); compare(vertices, packed);
        double[][] translations = {{0, -0.0, 0}, {0.25, -1.125, 35.0625},
                {Double.MIN_VALUE, -Double.MIN_VALUE, 1e-50}, {Double.MAX_VALUE, Double.NaN, -Double.MAX_VALUE}};
        for (double[] t : translations) for (boolean mirror : new boolean[]{false, true}) {
            ObjectArrayList<StoredVertexData> expected = new ObjectArrayList<>();
            vertices.forEach(v -> expected.add(v.modify(t[0], t[1], t[2], mirror)));
            PackedVertices transformed = new PackedVertices(); transformed.appendTransformed(packed, t[0], t[1], t[2], mirror);
            compare(expected, transformed, true);
        }
        PackedVertices repeated = new PackedVertices(); repeated.append(vertices); repeated.append(vertices);
        ObjectArrayList<StoredVertexData> twice = new ObjectArrayList<>(vertices); twice.addAll(vertices); compare(twice, repeated);
        compare(new ObjectArrayList<>(), new PackedVertices());

        // Native merges materialize the current source and apply each transform in order.
        // Later source changes must not leak into an already merged destination.
        PackedVertices changingSource = new PackedVertices(); changingSource.append(vertices);
        PackedVertices snapshotView = new PackedVertices();
        snapshotView.appendTransformed(changingSource, 0.1, -0.0, 16777217, true);
        ObjectArrayList<StoredVertexData> snapshotExpected = new ObjectArrayList<>();
        vertices.forEach(v -> snapshotExpected.add(v.modify(0.1, -0.0, 16777217, true)));
        changingSource.append(vertices);
        compare(snapshotExpected, snapshotView, true);
        PackedVertices nested = new PackedVertices();
        nested.appendTransformed(snapshotView, -0.1, 0.0, -16777216, true);
        ObjectArrayList<StoredVertexData> nestedExpected = new ObjectArrayList<>();
        snapshotExpected.forEach(v -> nestedExpected.add(v.modify(-0.1, 0.0, -16777216, true)));
        compare(nestedExpected, nested, true);

        ResourceLocation first = ResourceLocation.fromNamespaceAndPath("test", "first.png");
        ResourceLocation second = ResourceLocation.fromNamespaceAndPath("test", "second.png");
        NewOptimizedModelGroup original = new NewOptimizedModelGroup();
        PackedModelGroupStore<ResourceLocation> store = new PackedModelGroupStore<>();
        ObjectArrayList<AABB> boxes = new ObjectArrayList<>();
        ObjectArrayList<StoredVertexData> small = new ObjectArrayList<>();
        small.add(createVertex(-0.0F, 2, -3, new Color(20, 30, 40, 0), 0.3F, 0.7F, 0, -1, 0));
        small.add(createVertex(4, -5, 6, new Color(50, 60, 70, 127), 0, 1, 1, 0, 0));
        add(original, store, boxes, null, first, small, null);
        add(original, store, boxes, RenderStage.INTERIOR_TRANSLUCENT, second, small, new ObjectArrayList<>());
        add(original, store, boxes, RenderStage.LIGHT, first, new ObjectArrayList<>(), null);
        add(original, store, boxes, null, first, small, null);
        for (boolean mirror : new boolean[]{false, true}) {
            NewOptimizedModelGroup merged = new NewOptimizedModelGroup();
            PackedModelGroupStore<ResourceLocation> mergedStore = new PackedModelGroupStore<>();
            merged.merge(original, RenderStage.EXTERIOR, 2.3, -0.0, -5.625, mirror);
            mergedStore.merge(store, RenderStage.EXTERIOR, 2.3, -0.0, -5.625, mirror);
            compareGroup(merged, mergedStore);
            if (!merged.boxes.isEmpty()) throw new AssertionError("Release merge unexpectedly copied boxes");
        }

        ObjectArrayList<StoredVertexData> regular = new ObjectArrayList<>();
        for (int i = 0; i < 100000; i++) regular.add(createVertex(i % 100, i / 100F, 0,
                Color.WHITE, (i % 4) / 4F, (i % 8) / 8F, 0, 0, 1));
        PackedVertices regularPacked = new PackedVertices(); regularPacked.append(regular); compare(regular, regularPacked);
        String report = "{\"comparisons\":" + comparisons + ",\"mismatches\":0,\"random_vertices\":" + vertices.size()
                + ",\"checked_vertices\":" + checkedVertices + ",\"arithmetic_nan_payload_variations\":" + arithmeticNaNPayloadVariations
                + ",\"random_payload_bytes\":" + packed.payloadBytes() + ",\"regular_vertices\":" + regular.size()
                + ",\"regular_payload_bytes\":" + regularPacked.payloadBytes() + "}";
        System.out.println(report);
        if (args.length > 0) Files.writeString(Path.of(args[0]), report + "\n");
    }
}
