package site.benli06;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.mtr.libraries.de.javagl.obj.*;

/** Allocation control with explicit fixture limits; neither GL nor a production heap claim. */
public final class StreamingObjInputAudit {
    private static final byte[] MODEL = "g body\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n".getBytes(StandardCharsets.UTF_8);
    private static final byte[] COMMENT = "# bounded comment line\n".getBytes(StandardCharsets.UTF_8);
    private static InputStream generated(long comments) {
        return new InputStream() {
            long position;
            @Override public int read() {
                if (position >= MODEL.length + comments) return -1;
                long at = position++;
                return at < MODEL.length ? MODEL[(int) at] : COMMENT[(int) ((at - MODEL.length) % COMMENT.length)];
            }
            @Override public int read(byte[] bytes, int offset, int length) {
                java.util.Objects.checkFromIndexSize(offset, length, bytes.length);
                if (length == 0) return 0;
                int count = 0;
                while (count < length) { int next = read(); if (next < 0) break; bytes[offset + count++] = (byte) next; }
                return count == 0 ? -1 : count;
            }
        };
    }
    public static void main(String[] args) throws Exception {
        Path directory = Path.of(args[0]); Files.createDirectories(directory);
        String mode = args[1]; long comments = Long.parseLong(args[2]);
        long units = Math.addExact(MODEL.length, comments);
        var admission = new ReadAdmission(1, units, Math.multiplyExact(4L, units));
        Obj actual; String digest;
        if (mode.equals("snapshot")) {
            try (var source = generated(comments); var snapshot = ResourceTextSnapshot.capture(source, StandardCharsets.UTF_8, admission, directory);
                 var input = snapshot.utf8Stream()) {
                if (snapshot.length() != units) throw new AssertionError("Decoded length mismatch");
                digest = snapshot.digest(); actual = ObjReader.read(input);
            }
        } else if (mode.equals("string")) {
            try (var source = generated(comments)) {
                String raw = SegmentedResourceText.read(source, StandardCharsets.UTF_8, admission, directory);
                digest = ResourceTextDigest.sha256(raw);
                try (var input = org.apache.commons.io.IOUtils.toInputStream(raw, StandardCharsets.UTF_8)) { actual = ObjReader.read(input); }
            }
        } else throw new IllegalArgumentException("Unknown audit mode");
        var expectedHash = MessageDigest.getInstance("SHA-256");
        try (var source = generated(comments)) {
            byte[] bytes = new byte[8192]; for (int count; (count = source.read(bytes)) != -1;) expectedHash.update(bytes, 0, count);
        }
        if (!digest.equals(HexFormat.of().formatHex(expectedHash.digest()))) throw new AssertionError("Digest mismatch");
        Obj reference;
        try (var source = new ByteArrayInputStream(MODEL)) { reference = ObjReader.read(source); }
        var expected = new StringWriter(); var received = new StringWriter();
        ObjWriter.write(reference, expected); ObjWriter.write(actual, received);
        if (!expected.toString().equals(received.toString())) throw new AssertionError("Native OBJ differs");
        long[] workspace = admission.workspaceStatistics();
        if (admission.active() != 0 || workspace[1] != 0 || workspace[3] != 0) throw new AssertionError("Ownership did not settle");
        try (var files = Files.list(directory)) { if (files.findAny().isPresent()) throw new AssertionError("Snapshot leaked"); }
        System.out.println("{\"mode\":\"" + mode + "\",\"max_heap_bytes\":" + Runtime.getRuntime().maxMemory()
                + ",\"decoded_units\":" + units + ",\"explicit_fixture_workspace_bytes\":" + 4L * units
                + ",\"digest\":\"" + digest + "\",\"native_obj_equal\":true,\"settled\":true}");
    }
}
