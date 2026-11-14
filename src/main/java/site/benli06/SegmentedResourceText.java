package site.benli06;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.OutputStream;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Decodes native resource text without repeatedly growing its complete backing array. */
public final class SegmentedResourceText {
    private SegmentedResourceText() {}

    public static String read(InputStream input, Charset charset) throws IOException {
        return read(input, charset, ReadAdmission.GLOBAL);
    }

    public static String read(InputStream input, Charset charset, ReadAdmission admission) throws IOException {
        return read(input, charset, admission, null);
    }

    static String read(InputStream input, Charset charset, ReadAdmission admission, Path temporaryDirectory) throws IOException {
        try (var scope = admission.open()) {
            // The native resource helper owns and closes the original stream.
            InputStreamReader reader = new InputStreamReader(input, charset == null ? Charset.defaultCharset() : charset);
            char[] buffer = new char[8192];
            List<String> segments = new ArrayList<>();
            long length = 0;
            TextWorkspace workspace = admission.workspace();
            try (Snapshot snapshot = new Snapshot(temporaryDirectory);
                 var share = workspace.claim(workspace.share())) {
                for (int count; (count = reader.read(buffer)) != -1;) {
                    length += count;
                    admission.checkLength(length);
                    if (count == 0) continue;
                    if (!snapshot.exists() && 4L * length > workspace.share()) {
                        snapshot.begin(segments, admission);
                        segments.clear();
                        // No payload reservation is held while awaiting a larger atomic claim.
                        share.close();
                    }
                    if (snapshot.exists()) snapshot.write(buffer, count, admission);
                    else segments.add(new String(buffer, 0, count));
                }
                admission.checkLength(length);
                if (!snapshot.exists()) return String.join("", segments);
                snapshot.finish();
                try (var full = workspace.claim(4L * length)) {
                    return snapshot.restore(length, admission);
                }
            }
        }
    }

    /** Immutable decoded UTF-16 snapshot; never reopens a mutable resource provider. */
    private static final class Snapshot implements AutoCloseable {
        private final Path directory;
        private Path path;
        private OutputStream output;
        private byte[] bytes;
        Snapshot(Path directory) { this.directory = directory; }
        boolean exists() { return path != null; }
        void begin(List<String> segments, ReadAdmission admission) throws IOException {
            path = directory == null ? Files.createTempFile("mtr-memory-text-", ".utf16")
                    : Files.createTempFile(directory, "mtr-memory-text-", ".utf16");
            output = new BufferedOutputStream(Files.newOutputStream(path));
            bytes = new byte[8192];
            char[] chars = new char[4096];
            for (String segment : segments) {
                for (int offset = 0; offset < segment.length();) {
                    int count = Math.min(chars.length, segment.length() - offset);
                    segment.getChars(offset, offset + count, chars, 0);
                    write(chars, count, admission); offset += count;
                }
            }
        }
        void write(char[] chars, int count, ReadAdmission admission) throws IOException {
            for (int offset = 0; offset < count;) {
                admission.checkLength(0);
                int units = Math.min(bytes.length / 2, count - offset);
                for (int i = 0; i < units; i++) {
                    char c = chars[offset + i]; bytes[2 * i] = (byte) (c >>> 8); bytes[2 * i + 1] = (byte) c;
                }
                output.write(bytes, 0, 2 * units); offset += units;
            }
        }
        void finish() throws IOException {
            OutputStream stream = output; output = null; stream.close();
        }
        String restore(long expected, ReadAdmission admission) throws IOException {
            var segments = new ArrayList<String>();
            char[] chars = new char[4096];
            long total = 0;
            int used = 0, high = -1;
            try (var stream = new BufferedInputStream(Files.newInputStream(path))) {
                for (int count; (count = stream.read(bytes)) != -1;) {
                    admission.checkLength(total);
                    for (int i = 0; i < count; i++) {
                        int b = bytes[i] & 255;
                        if (high < 0) high = b;
                        else {
                            if (++total > expected) throw new IOException("Text snapshot exceeds its decoded length");
                            chars[used++] = (char) ((high << 8) | b); high = -1;
                            if (used == chars.length) { segments.add(new String(chars)); used = 0; }
                        }
                    }
                }
            }
            if (high >= 0 || total != expected) throw new IOException("Text snapshot decoded length mismatch");
            admission.checkLength(total);
            if (used != 0) segments.add(new String(chars, 0, used));
            return String.join("", segments);
        }
        @Override public void close() throws IOException {
            IOException failure = null;
            try { if (output != null) output.close(); } catch (IOException error) { failure = error; }
            try { if (path != null) Files.delete(path); }
            catch (IOException error) { if (failure == null) failure = error; else failure.addSuppressed(error); }
            if (failure != null) throw failure;
        }
    }
}
