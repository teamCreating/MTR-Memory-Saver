package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Optional;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicInteger;
import net.minecraft.resources.ResourceLocation;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import org.mtr.core.serializer.JsonWriter;
import org.mtr.libraries.com.google.gson.JsonObject;
import org.mtr.resource.ResourceProvider;

@Timeout(20)
class ResourceTextSnapshotTest {
    @TempDir Path directory;

    @Test void boundedReaderPreservesReplacementSupplementaryTextAndOriginalDigest() throws Exception {
        for (String text : new String[]{"", "a".repeat(19000), "\u03b1".repeat(8191) + "\ud83d\ude86" + "\u0000\u4e2d".repeat(4000)}) {
            for (var charset : new java.nio.charset.Charset[]{StandardCharsets.UTF_8, StandardCharsets.UTF_16LE}) {
                byte[] bytes = text.getBytes(charset);
                checkSnapshot(bytes, charset, new String(bytes, charset));
            }
        }
        byte[] malformed = {(byte) 0xc0, (byte) 0xaf, (byte) 0xe2, (byte) 0x82};
        checkSnapshot(malformed, StandardCharsets.UTF_8, new String(malformed, StandardCharsets.UTF_8));
    }

    @Test void readerDigestMatchesOldStringBytesAcrossEverySurrogateBoundary() throws Exception {
        for (String text : new String[]{"\ud800", "\udc00", "\ud800x\udc00", "x".repeat(4095) + "\ud83d\ude86" + "\ud800" + "y".repeat(4095)}) {
            String expected = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8)));
            for (int chunk : new int[]{1, 2, 4095, 4096, 8192}) {
                Reader reader = new StringReader(text) {
                    @Override public int read(char[] chars, int offset, int length) throws IOException {
                        return super.read(chars, offset, Math.min(chunk, length));
                    }
                };
                assertEquals(expected, ResourceTextDigest.sha256(reader));
            }
        }
    }

    @Test void sourceMutationAfterCaptureCannotChangeDigestOrParsedInput() throws Exception {
        byte[] bytes = "{\"name\":\"original\"}".getBytes(StandardCharsets.UTF_8);
        var admission = new ReadAdmission(1, 1000);
        try (var snapshot = ResourceTextSnapshot.capture(new ByteArrayInputStream(bytes), StandardCharsets.UTF_8, admission, directory)) {
            java.util.Arrays.fill(bytes, (byte) 'x');
            try (var reader = snapshot.reader()) {
                assertEquals("original", org.mtr.libraries.com.google.gson.JsonParser.parseReader(reader).getAsJsonObject().get("name").getAsString());
            }
        }
        clean(admission);
    }

    @Test void readerAndStringKeepNativeBlockbenchSchemaAndMalformedInputFailures() throws Exception {
        for (String text : new String[]{"{}", "{\"meta\":{\"format_version\":\"4.10\"},\"resolution\":{\"width\":32,\"height\":16},\"elements\":[],\"outliner\":[],\"textures\":[]}"}) {
            var expected = SharedBlockbenchCache.parseInput(text);
            var actual = SharedBlockbenchCache.parseInput(new StringReader(text));
            JsonObject expectedJson = new JsonObject(), actualJson = new JsonObject();
            expected.serializeFullData(new JsonWriter(expectedJson)); actual.serializeFullData(new JsonWriter(actualJson));
            assertEquals(expectedJson, actualJson);
        }
        for (String text : new String[]{"", "{", "[]", "null", "{\"elements\":[", "{} garbage"}) {
            assertThrows(RuntimeException.class, () -> SharedBlockbenchCache.parseInput(new StringReader(text)), text);
        }
        IOException readError = new IOException("reader failed");
        Reader broken = new Reader() {
            @Override public int read(char[] chars, int offset, int length) throws IOException { throw readError; }
            @Override public void close() {}
        };
        assertSame(readError, assertThrows(org.mtr.libraries.com.google.gson.JsonIOException.class,
                () -> SharedBlockbenchCache.parseInput(broken)).getCause());
    }

    @Test void unknownAndDecliningProvidersKeepTheirActualGetContract() throws Exception {
        var model = ResourceLocation.parse("mtr:test.bbmodel");
        var texture = ResourceLocation.parse("mtr:test.png");
        AtomicInteger gets = new AtomicInteger(), opens = new AtomicInteger();
        ResourceProvider custom = resource -> { assertEquals(model, resource); gets.incrementAndGet(); return "{}"; };
        var fallback = SharedBlockbenchCache.prepare(model, texture, custom, false);
        assertEquals(1, gets.get()); assertNull(fallback.owner());
        var declining = new SnapshotResourceProvider(custom, resource -> { opens.incrementAndGet(); return Optional.empty(); });
        var declined = SharedBlockbenchCache.prepare(model, texture, declining, false);
        assertEquals(2, gets.get()); assertEquals(1, opens.get()); assertEquals(fallback.contentKey(), declined.contentKey());
        assertSame(custom, declining.delegate());
        ResourceProvider missing = resource -> null;
        assertThrows(IllegalStateException.class, () -> SharedBlockbenchCache.prepare(model, texture, missing, false));
    }

    @Test void explicitCapabilityAvoidsGetAndKeepsTheSameContentKey() throws Exception {
        var model = ResourceLocation.parse("mtr:test.bbmodel");
        var texture = ResourceLocation.parse("mtr:test.png");
        var admission = new ReadAdmission(1, 1000);
        var snapshot = ResourceTextSnapshot.capture(new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission, directory);
        ResourceProvider original = resource -> fail("Streaming capability called original get");
        var provider = new SnapshotResourceProvider(original, resource -> Optional.of(snapshot));
        var streaming = SharedBlockbenchCache.prepare(model, texture, provider, false);
        var fallback = SharedBlockbenchCache.prepare(model, texture, resource -> "{}", false);
        assertEquals(fallback.contentKey(), streaming.contentKey()); assertSame(snapshot, streaming.owner());
        streaming.owner().close(); clean(admission);
    }

    @Test void sourceCountersKeepLateOldProviderCompletionsInTheirOriginalEpoch() throws Exception {
        var resource = ResourceLocation.parse("mtr:test.bbmodel");
        SnapshotResourceProvider.beginReload();
        var old = new SnapshotResourceProvider(id -> "{}", id -> Optional.empty());
        SnapshotResourceProvider.beginReload();
        old.snapshot(resource);
        assertEquals(new SnapshotResourceProvider.Statistics(0, 0, 0, 0, 0), SnapshotResourceProvider.statistics());
        var admission = new ReadAdmission(1, 1000);
        var current = new SnapshotResourceProvider(id -> "{}", id -> {
            try { return Optional.of(ResourceTextSnapshot.capture(new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission, directory)); }
            catch (IOException error) { throw new java.io.UncheckedIOException(error); }
        });
        try (var captured = current.snapshot(resource).orElseThrow()) { assertEquals(2, captured.length()); }
        var decline = new SnapshotResourceProvider(id -> "{}", id -> Optional.empty()); decline.snapshot(resource);
        var failure = new SnapshotResourceProvider(id -> "{}", id -> { throw new IllegalStateException("capture failed"); });
        assertThrows(IllegalStateException.class, () -> failure.snapshot(resource));
        assertEquals(new SnapshotResourceProvider.Statistics(3, 1, 1, 1, 2), SnapshotResourceProvider.statistics());
        SnapshotResourceProvider.beginReload(); clean(admission);
    }

    @Test void captureFailureLimitCancellationAndSourceCloseFailureCannotLeakOwner() throws Exception {
        var admission = new ReadAdmission(1, 1000);
        assertThrows(IllegalStateException.class, () -> ResourceTextSnapshot.capture(
                new ByteArrayInputStream(new byte[1001]), StandardCharsets.UTF_8, admission, directory));
        clean(admission);
        IOException failure = new IOException("read failed");
        InputStream broken = new InputStream() { @Override public int read() throws IOException { throw failure; } };
        assertSame(failure, assertThrows(IOException.class, () -> ResourceTextSnapshot.capture(broken, StandardCharsets.UTF_8, admission, directory)));
        clean(admission);
        try {
            Thread.currentThread().interrupt();
            assertThrows(CancellationException.class, () -> ResourceTextSnapshot.capture(new ByteArrayInputStream(new byte[0]), StandardCharsets.UTF_8, admission, directory));
        } finally { Thread.interrupted(); }
        clean(admission);
        IOException closeFailure = new IOException("source close failed");
        assertSame(closeFailure, assertThrows(IOException.class, () -> ResourceTextSnapshot.open(() ->
                new ByteArrayInputStream(new byte[0]) { @Override public void close() throws IOException { throw closeFailure; } },
                StandardCharsets.UTF_8, admission, directory)));
        clean(admission);
    }

    @Test void ownedSnapshotHandlesShortIoAndPropagatesCreateWriteReadRewindCloseErrors() throws Exception {
        for (var fault : new SnapshotFaultFileSystem.Fault[]{SnapshotFaultFileSystem.Fault.CREATE,
                SnapshotFaultFileSystem.Fault.WRITE, SnapshotFaultFileSystem.Fault.READ,
                SnapshotFaultFileSystem.Fault.REWIND, SnapshotFaultFileSystem.Fault.TRUNCATE_ON_REWIND,
                SnapshotFaultFileSystem.Fault.UNSUPPORTED}) {
            var filesystem = new SnapshotFaultFileSystem(fault);
            var admission = new ReadAdmission(1, 20000);
            assertThrows(Exception.class, () -> ResourceTextSnapshot.capture(new ByteArrayInputStream("\u03b1".repeat(15000).getBytes(StandardCharsets.UTF_8)),
                    StandardCharsets.UTF_8, admission, filesystem.wrap(directory)));
            clean(admission);
        }
    }

    @Test void snapshotShortIoPreservesBytesAndOwnerCloseErrorIsNotSuccess() throws Exception {
        var admission = new ReadAdmission(1, 20000);
        var shortIo = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.SHORT_IO);
        String text = "\u03b1\ud83d\ude86".repeat(4000);
        try (var snapshot = ResourceTextSnapshot.capture(new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)),
                StandardCharsets.UTF_8, admission, shortIo.wrap(directory)); var reader = snapshot.reader()) {
            assertEquals(ResourceTextDigest.sha256(text), snapshot.digest());
            assertEquals(snapshot.digest(), ResourceTextDigest.sha256(reader));
        }
        clean(admission);
        var closeError = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.CLOSE);
        var snapshot = ResourceTextSnapshot.capture(new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)),
                StandardCharsets.UTF_8, admission, closeError.wrap(directory));
        assertSame(closeError.closeFailure, assertThrows(IOException.class, snapshot::close));
        clean(admission);
    }

    @Test void closingAnOldReaderTwiceCannotReleaseTheCurrentReaderGuard() throws Exception {
        var admission = new ReadAdmission(1, 1000);
        try (var snapshot = ResourceTextSnapshot.capture(new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)), StandardCharsets.UTF_8, admission, directory)) {
            var first = snapshot.reader(); first.close();
            try (var second = snapshot.reader()) {
                first.close();
                assertThrows(IOException.class, snapshot::reader);
                assertEquals('{', second.read()); assertEquals('}', second.read()); assertEquals(-1, second.read());
            }
            try (var third = snapshot.reader()) { assertEquals('{', third.read()); }
        }
        clean(admission);
    }

    @Test void zeroProgressReadsAndWritesStillObserveRetirementAndDeleteTheirOwner() throws Exception {
        for (var fault : new SnapshotFaultFileSystem.Fault[]{SnapshotFaultFileSystem.Fault.ZERO_READ, SnapshotFaultFileSystem.Fault.ZERO_WRITE}) {
            var filesystem = new SnapshotFaultFileSystem(fault);
            var retired = new java.util.concurrent.atomic.AtomicBoolean();
            filesystem.onZeroProgress = () -> retired.set(true);
            var admission = new ReadAdmission(1, 1000);
            try (var scope = admission.open(retired::get)) {
                assertThrows(CancellationException.class, () -> ResourceTextSnapshot.capture(new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)),
                        StandardCharsets.UTF_8, admission, filesystem.wrap(directory)));
            }
            assertEquals(1, filesystem.closeCalls); clean(admission);
        }
    }

    @Test void snapshotWriteErrorKeepsItsOriginalCauseAndSuppressedCloseError() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.WRITE_AND_CLOSE);
        var admission = new ReadAdmission(1, 1000);
        var error = assertThrows(IOException.class, () -> ResourceTextSnapshot.capture(new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8)),
                StandardCharsets.UTF_8, admission, filesystem.wrap(directory)));
        assertSame(filesystem.writeFailure, error); assertArrayEquals(new Throwable[]{filesystem.closeFailure}, error.getSuppressed());
        clean(admission);
    }

    private void checkSnapshot(byte[] bytes, java.nio.charset.Charset charset, String expected) throws Exception {
        var admission = new ReadAdmission(2, 25000);
        try (var snapshot = ResourceTextSnapshot.capture(new ByteArrayInputStream(bytes), charset, admission, directory)) {
            assertEquals(expected.length(), snapshot.length()); assertEquals(ResourceTextDigest.sha256(expected), snapshot.digest());
            for (int pass = 0; pass < 2; pass++) {
                try (Reader reader = snapshot.reader()) {
                    StringBuilder actual = new StringBuilder(); char[] chars = new char[137];
                    for (int count; (count = reader.read(chars)) != -1;) actual.append(chars, 0, count);
                    assertEquals(expected, actual.toString());
                }
            }
        }
        clean(admission);
    }

    private void clean(ReadAdmission admission) throws IOException {
        assertEquals(0, admission.active()); assertEquals(0, admission.workspaceStatistics()[1]);
        assertEquals(0, admission.workspaceStatistics()[3]);
        try (var files = Files.list(directory)) { assertEquals(0, files.count()); }
    }
}
