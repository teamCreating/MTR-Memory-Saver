package site.benli06;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.Charset;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

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
                snapshot.rewind();
                try (var full = workspace.claim(4L * length)) {
                    return snapshot.restore(length, admission);
                }
            }
        }
    }

    /** Immutable decoded UTF-16 snapshot; never reopens a mutable resource provider. */
    private static final class Snapshot implements AutoCloseable {
        private final Path directory;
        private SeekableByteChannel channel;
        private byte[] bytes;
        private ByteBuffer buffer;
        Snapshot(Path directory) { this.directory = directory; }
        boolean exists() { return channel != null; }
        void begin(List<String> segments, ReadAdmission admission) throws IOException {
            Path parent = directory == null ? Path.of(System.getProperty("java.io.tmpdir")) : directory;
            FileAttribute<?>[] attributes = parent.getFileSystem().supportedFileAttributeViews().contains("posix")
                    ? new FileAttribute<?>[]{PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------"))}
                    : new FileAttribute<?>[0];
            while (channel == null) {
                admission.checkLength(0);
                Path path = parent.resolve("mtr-memory-text-" + UUID.randomUUID() + ".utf16");
                try {
                    // Creating and taking delete-on-close ownership is one operation:
                    // no abrupt-exit gap exists between creating and reopening a file.
                    channel = Files.newByteChannel(path, java.util.Set.of(StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.READ, StandardOpenOption.WRITE, StandardOpenOption.DELETE_ON_CLOSE), attributes);
                } catch (FileAlreadyExistsException collision) {
                    // A name collision belongs to another owner; never delete or reuse it.
                }
            }
            bytes = new byte[8192];
            buffer = ByteBuffer.wrap(bytes);
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
                buffer.clear().limit(2 * units);
                while (buffer.hasRemaining()) {
                    admission.checkLength(0);
                    if (channel.write(buffer) == 0) Thread.yield();
                }
                offset += units;
            }
        }
        void rewind() throws IOException {
            // Direct channel writes have no pending stream buffer. Keep the owner
            // open while waiting for restoration's larger workspace reservation.
            channel.position(0);
        }
        String restore(long expected, ReadAdmission admission) throws IOException {
            var segments = new ArrayList<String>();
            char[] chars = new char[4096];
            long total = 0;
            int used = 0, high = -1;
            while (true) {
                admission.checkLength(total);
                buffer.clear();
                int count = channel.read(buffer);
                if (count < 0) break;
                if (count == 0) { Thread.yield(); continue; }
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
            if (high >= 0 || total != expected) throw new IOException("Text snapshot decoded length mismatch");
            admission.checkLength(total);
            if (used != 0) segments.add(new String(chars, 0, used));
            return String.join("", segments);
        }
        @Override public void close() throws IOException {
            SeekableByteChannel owned = channel;
            channel = null;
            if (owned != null) owned.close();
        }
    }
}
