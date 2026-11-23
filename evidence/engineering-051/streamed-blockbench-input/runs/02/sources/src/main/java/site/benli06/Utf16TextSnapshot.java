package site.benli06;

import java.io.IOException;
import java.io.Reader;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/** One delete-on-close channel owns decoded UTF-16 from capture through consumption. */
final class Utf16TextSnapshot implements AutoCloseable {
    private final Path directory;
    private SeekableByteChannel channel;
    private byte[] bytes;
    private ByteBuffer buffer;
    private boolean activeReader;

    Utf16TextSnapshot(Path directory) { this.directory = directory; }
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
                channel = Files.newByteChannel(path, java.util.Set.of(StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.READ, StandardOpenOption.WRITE, StandardOpenOption.DELETE_ON_CLOSE), attributes);
            } catch (FileAlreadyExistsException collision) {
                // A collision belongs to another owner; never delete or reuse it.
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

    void rewind() throws IOException { channel.position(0); }

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

    /** A bounded view; closing it leaves the channel with its explicit snapshot owner. */
    Reader reader(long expected, ReadAdmission admission) throws IOException {
        if (channel == null) throw new IOException("Text snapshot is closed");
        if (activeReader) throw new IOException("Text snapshot already has a reader");
        if (channel.size() != Math.multiplyExact(2L, expected))
            throw new IOException("Text snapshot decoded length mismatch");
        rewind();
        activeReader = true;
        return new Reader() {
            private long units;
            private boolean closed;
            @Override public int read(char[] chars, int offset, int length) throws IOException {
                Objects.checkFromIndexSize(offset, length, chars.length);
                if (closed || channel == null) throw new IOException("Text snapshot reader is closed");
                admission.checkLength(units);
                if (length == 0) return 0;
                if (units == expected) return -1;
                int count = (int) Math.min(Math.min(length, bytes.length / 2), expected - units);
                buffer.clear().limit(2 * count);
                while (buffer.hasRemaining()) {
                    admission.checkLength(units);
                    int read = channel.read(buffer);
                    if (read < 0) throw new IOException("Text snapshot decoded length mismatch");
                    if (read == 0) Thread.yield();
                }
                buffer.flip();
                for (int i = 0; i < count; i++) chars[offset + i] = buffer.getChar();
                units += count;
                return count;
            }
            @Override public void close() { if (!closed) { closed = true; activeReader = false; } }
        };
    }

    @Override public void close() throws IOException {
        SeekableByteChannel owned = channel;
        channel = null;
        activeReader = false;
        if (owned != null) owned.close();
    }
}
