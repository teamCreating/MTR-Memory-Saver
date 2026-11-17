package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.resources.ResourceLocation;
import org.apache.commons.io.IOUtils;
import org.junit.jupiter.api.Test;
import org.mtr.libraries.de.javagl.obj.*;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;
import org.mtr.model.ObjModelLoader;
import org.mtr.resource.VehicleModel;

class ObjInputSnapshotTest {
    @Test void boundedUtf8BridgePreservesNativeStringBytesAcrossSurrogatesAndReadSizes() throws Exception {
        for (int boundary : new int[] {0, 1, 127, 4095, 8191, 8192, 16383}) {
            for (String tail : List.of("", "é中😀", "\ud800", "\udc00", "\ud800x", "😀\ud800\udc00")) {
                String text = "x".repeat(boundary) + tail;
                for (int chunk : new int[] {1, 7, 8192}) {
                    var bytes = new ByteArrayOutputStream();
                    try (var input = ResourceTextSnapshot.utf8Stream(new StringReader(text))) {
                        byte[] buffer = new byte[chunk];
                        for (int count; (count = input.read(buffer)) != -1;) bytes.write(buffer, 0, count);
                    }
                    assertArrayEquals(text.getBytes(StandardCharsets.UTF_8), bytes.toByteArray());
                }
            }
        }
    }

    @Test void streamClosesItsReaderAndAllowsSnapshotOwnershipToCloseSeparately() throws Exception {
        var closed = new AtomicInteger();
        var reader = new StringReader("v 0 0 0") { @Override public void close() { closed.incrementAndGet(); super.close(); } };
        try (var input = ResourceTextSnapshot.utf8Stream(reader)) { input.readAllBytes(); }
        assertEquals(1, closed.get());
        var admission = new ReadAdmission(1, 10000);
        try (var snapshot = ResourceTextSnapshot.open(() -> new ByteArrayInputStream("# x\nv 0 0 0\n".getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission)) {
            try (var input = snapshot.utf8Stream()) { assertEquals(1, ObjReader.read(input).getNumVertices()); }
            try (var input = snapshot.utf8Stream()) { assertEquals(1, ObjReader.read(input).getNumVertices()); }
        }
        assertEquals(0, admission.active());
    }

    @Test void objInputRetainsNativeAsciiConversionGroupsIndicesAndMaterialNames() throws Exception {
        for (String newline : List.of("\n", "\r\n", "\r")) {
            String text = String.join(newline, "# é中😀", "mtllib matérial.mtl", "g grüp", "usemtl rôuge",
                    "v 0 0 0", "v 1 0 0", "v 0 1 0", "vt 0 0", "vt 1 0", "vt 0 1", "vn 0 0 1", "f -3/1/1 -2/2/1 -1/3/1", "");
            Obj reference;
            try (var input = IOUtils.toInputStream(text, StandardCharsets.UTF_8)) { reference = ObjReader.read(input); }
            try (var input = ResourceTextSnapshot.utf8Stream(new StringReader(text))) {
                Obj actual = ObjReader.read(input);
                assertEquals(write(reference), write(actual));
                assertEquals(reference.getMtlFileNames(), actual.getMtlFileNames());
                assertEquals(ObjSplitting.splitByGroups(reference).keySet(), ObjSplitting.splitByGroups(actual).keySet());
                assertEquals(ObjSplitting.splitByMaterialGroups(reference).keySet(), ObjSplitting.splitByMaterialGroups(actual).keySet());
            }
        }
    }

    @Test void materialStreamPreservesNativeDefaultCharsetAndAllWriterProperties() throws Exception {
        String text = "newmtl café😀\nKa .1 .2 .3\nKd .2 .4 .6\nKs .5 .6 .7\nNs 12\nd .4\nillum 2\nmap_Kd -s 1 2 3 texé.png\n";
        List<Mtl> expected;
        try (var input = IOUtils.toInputStream(text, StandardCharsets.UTF_8)) { expected = MtlReader.read(input); }
        try (var input = ResourceTextSnapshot.utf8Stream(new StringReader(text))) {
            assertEquals(writeMaterials(expected), writeMaterials(MtlReader.read(input)));
        }
    }

    @Test void pathAndTextureRulesMatchExactNativePrivateResolvers() throws Exception {
        var path = ObjModelLoader.class.getDeclaredMethod("formatFilePath", String.class); path.setAccessible(true);
        for (String name : List.of("a.mtl", "a\\b.mtl", "a\\\\b.mtl", "a\\\\\\b.mtl", "../x.mtl"))
            assertEquals(path.invoke(null, name), StreamedObjCache.materialPath(name));
        var texture = VehicleModel.class.getDeclaredMethod("lambda$getModelLoaderBase$4", ResourceLocation.class, String.class, String.class);
        texture.setAccessible(true);
        var fallback = ResourceLocation.fromNamespaceAndPath("fixture", "textures/default.png");
        for (String name : Arrays.asList(null, "", "default.png", "other.png", "../body.png", "fixture:body.png"))
            assertEquals(texture.invoke(null, fallback, "fixture:models/car.obj", name), StreamedObjCache.texture("fixture:models/car.obj", fallback, name));
    }

    @Test void materialLookupKeepsNativeNormalizationAndLastMaterialDefinition() throws Exception {
        String objText = "mtllib one.mtl two.mtl\nv 0 0 0\n";
        Obj obj;
        try (var input = IOUtils.toInputStream(objText, StandardCharsets.UTF_8)) { obj = ObjReader.read(input); }
        var files = Map.of("one.mtl", "newmtl paint\nKd 1 0 0\n", "two.mtl", "newmtl paint\nKd 0 1 0\nnewmtl glass\nd .5\n");
        var admission = new ReadAdmission(1, 10000);
        var source = new SnapshotResourceProvider(id -> { throw new AssertionError("Unexpected String material fallback"); }, id -> {
            String text = files.get(id.getPath().substring(id.getPath().lastIndexOf('/') + 1));
            try { return Optional.of(ResourceTextSnapshot.open(() -> new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission)); }
            catch (IOException error) { throw new UncheckedIOException(error); }
        });
        var reference = new Object2ObjectOpenHashMap<String, Mtl>();
        var nativeLoad = ObjModelLoader.class.getDeclaredMethod("lambda$loadModel$1", java.util.function.Function.class, Object2ObjectOpenHashMap.class, String.class);
        nativeLoad.setAccessible(true);
        java.util.function.Function<String, String> resolver = files::get;
        for (String name : obj.getMtlFileNames()) nativeLoad.invoke(null, resolver, reference, name);
        var actual = StreamedObjCache.materials(obj, "fixture:models/car.obj", source);
        assertEquals(writeMaterials(reference.values()), writeMaterials(actual.values()));
        assertEquals(0, admission.active());
    }

    private static String write(Obj obj) throws IOException { var writer = new StringWriter(); ObjWriter.write(obj, writer); return writer.toString(); }
    private static String writeMaterials(Collection<Mtl> materials) throws IOException {
        var sorted = new ArrayList<>(materials); sorted.sort(Comparator.comparing(Mtl::getName));
        var writer = new StringWriter(); MtlWriter.write(sorted, writer); return writer.toString();
    }
}
