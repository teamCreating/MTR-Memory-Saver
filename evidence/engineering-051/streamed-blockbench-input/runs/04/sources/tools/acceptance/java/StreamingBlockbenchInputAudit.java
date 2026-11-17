package site.benli06;

import java.io.IOException;
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.mtr.core.serializer.JsonWriter;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Small-heap allocation control. Explicit fixture limits are not the production default policy. */
public final class StreamingBlockbenchInputAudit {
    private static final class JsonInput extends InputStream {
        private final long whitespace;
        private long position;
        JsonInput(long whitespace) { this.whitespace = whitespace; }
        @Override public int read() {
            if (position < whitespace) { position++; return ' '; }
            if (position++ == whitespace) return '{';
            return position == whitespace + 2 ? '}' : -1;
        }
        @Override public int read(byte[] bytes, int offset, int length) {
            java.util.Objects.checkFromIndexSize(offset, length, bytes.length);
            if (length == 0) return 0;
            int count = 0;
            while (count < length) { int value = read(); if (value < 0) break; bytes[offset + count++] = (byte) value; }
            return count == 0 ? -1 : count;
        }
    }

    public static void main(String[] arguments) throws Exception {
        Path directory = Path.of(arguments[0]); Files.createDirectories(directory);
        String mode = arguments[1]; long whitespace = Long.parseLong(arguments[2]);
        long units = Math.addExact(whitespace, 2);
        var admission = new ReadAdmission(1, units, Math.multiplyExact(4, units));
        if (!mode.equals("snapshot") && !mode.equals("string")) throw new IllegalArgumentException("Unknown input mode");
        String digest;
        org.mtr.resource.BlockbenchModel model;
        if (mode.equals("snapshot")) {
            try (InputStream input = new JsonInput(whitespace);
                 var snapshot = ResourceTextSnapshot.capture(input, StandardCharsets.UTF_8, admission, directory);
                 Reader reader = snapshot.reader()) {
                if (snapshot.length() != units) throw new AssertionError("Decoded length mismatch");
                digest = snapshot.digest(); model = SharedBlockbenchCache.parseInput(reader);
            }
        } else {
            try (InputStream input = new JsonInput(whitespace)) {
                String text = SegmentedResourceText.read(input, StandardCharsets.UTF_8, admission, directory);
                digest = ResourceTextDigest.sha256(text); model = SharedBlockbenchCache.parseInput(text);
            }
        }
        MessageDigest expected = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new JsonInput(whitespace)) {
            byte[] buffer = new byte[8192];
            for (int count; (count = input.read(buffer)) != -1;) expected.update(buffer, 0, count);
        }
        if (!digest.equals(HexFormat.of().formatHex(expected.digest()))) throw new AssertionError("Digest mismatch");
        JsonObject actual = new JsonObject(), baseline = new JsonObject();
        model.serializeFullData(new JsonWriter(actual));
        SharedBlockbenchCache.parseInput("{}").serializeFullData(new JsonWriter(baseline));
        if (!actual.equals(baseline)) throw new AssertionError("Native Blockbench serialization mismatch");
        if (admission.active() != 0 || admission.workspaceStatistics()[1] != 0 || admission.workspaceStatistics()[3] != 0)
            throw new AssertionError("Admission did not settle");
        try (var files = Files.list(directory)) { if (files.findAny().isPresent()) throw new AssertionError("Snapshot leaked"); }
        System.out.println("{\"mode\":\"" + mode + "\",\"max_heap_bytes\":" + Runtime.getRuntime().maxMemory()
                + ",\"decoded_units\":" + units + ",\"explicit_fixture_workspace_bytes\":" + 4 * units
                + ",\"digest\":\"" + digest + "\",\"native_schema_equal\":true,\"settled\":true}");
    }
}
