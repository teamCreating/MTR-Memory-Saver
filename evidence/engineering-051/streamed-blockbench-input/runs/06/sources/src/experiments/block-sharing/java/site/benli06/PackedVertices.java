package site.benli06;

import java.io.*;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.InflaterInputStream;
import org.mtr.model.StoredVertexData;
import org.mtr.MTR;

/** Lossless source blocks with immutable, snapshot-based transformed views. */
public final class PackedVertices {
    private record Payload(int count, byte[] bytes, int hash) {
        @Override public int hashCode() { return hash; }
        @Override public boolean equals(Object other) {
            return other instanceof Payload p && count == p.count && Arrays.equals(bytes, p.bytes);
        }
    }
    private static final ConcurrentHashMap<Payload, Block> POOL = new ConcurrentHashMap<>();
    private static final ReentrantReadWriteLock POOL_LOCK = new ReentrantReadWriteLock();
    private static final LongAdder REQUESTS = new LongAdder(), REQUESTED_BYTES = new LongAdder();
    private static final LongAdder UNIQUE_BLOCKS = new LongAdder(), UNIQUE_BYTES = new LongAdder();
    private static boolean sharing = true;

    public static void beginSharing() {
        var lock = POOL_LOCK.writeLock(); lock.lock();
        try {
            POOL.clear(); REQUESTS.reset(); REQUESTED_BYTES.reset();
            UNIQUE_BLOCKS.reset(); UNIQUE_BYTES.reset(); sharing = true;
        } finally { lock.unlock(); }
    }

    public static Map<String, Long> sharingStatistics() {
        var lock = POOL_LOCK.readLock(); lock.lock();
        try { return Map.of("requests", REQUESTS.sum(), "requested_payload_bytes", REQUESTED_BYTES.sum(),
                "unique_blocks", UNIQUE_BLOCKS.sum(), "unique_payload_bytes", UNIQUE_BYTES.sum()); }
        finally { lock.unlock(); }
    }

    public static void finishSharing() {
        var lock = POOL_LOCK.writeLock(); lock.lock();
        try { sharing = false; POOL.clear(); }
        finally { lock.unlock(); }
        var stats = sharingStatistics();
        MTR.LOGGER.info("MTR packed block sharing: {} requests / {} unique blocks, {} requested / {} unique payload bytes; pool released",
                stats.get("requests"), stats.get("unique_blocks"), stats.get("requested_payload_bytes"), stats.get("unique_payload_bytes"));
    }

    private static Block intern(int count, byte[] bytes) {
        var lock = POOL_LOCK.readLock(); lock.lock();
        try {
            if (!sharing) return new Block(count, bytes);
            REQUESTS.increment(); REQUESTED_BYTES.add(bytes.length);
            Payload key = new Payload(count, bytes, 31 * count + Arrays.hashCode(bytes));
            // Hash collisions compare the entire immutable compressed byte stream and count.
            // Labels, material stage, texture and vehicle state remain in independent stores.
            return POOL.computeIfAbsent(key, p -> {
                UNIQUE_BLOCKS.increment(); UNIQUE_BYTES.add(bytes.length);
                return new Block(count, bytes);
            });
        } finally { lock.unlock(); }
    }
    @FunctionalInterface
    public interface Sink {
        void vertex(float x, float y, float z, int argb, float u, float v,
                    float normalX, float normalY, float normalZ);
    }
    @FunctionalInterface private interface Source { void emit(Sink sink); }
    private sealed interface Segment permits Block, Transformed {
        int count();
        void emit(Sink sink);
    }
    private record Block(int count, byte[] bytes) implements Segment {
        public void emit(Sink sink) { decode(this, sink); }
    }
    private record Snapshot(int count, Segment[] segments) {
        void emit(Sink sink) { for (Segment segment : segments) segment.emit(sink); }
    }
    private record Transformed(Snapshot source, float x, float y, float z, int factor) implements Segment {
        public int count() { return source.count(); }
        public void emit(Sink sink) {
            // Keep every release multiply/add, including signed zero and float rounding.
            // Combining successive offsets or skipping identity transforms is not equivalent.
            source.emit((vx, vy, vz, color, u, v, nx, ny, nz) -> sink.vertex(
                    vx * factor + x, vy + y, vz * factor + z,
                    color, u, v, nx * factor, ny, nz * factor));
        }
    }
    private static final int RECORD_BYTES = 9 * Integer.BYTES;
    private static final int BUFFER_VERTICES = 1024;
    private Segment first;
    private ArrayList<Segment> additional;
    private Snapshot snapshot;
    private int size;

    public int size() { return size; }

    public long payloadBytes() {
        return payloadBytes(snapshot(), new IdentityHashMap<>());
    }

    private static long payloadBytes(Snapshot source, IdentityHashMap<Segment, Boolean> seen) {
        long total = 0;
        for (Segment segment : source.segments()) if (seen.put(segment, Boolean.TRUE) == null) {
            if (segment instanceof Block block) total += block.bytes().length;
            else total += payloadBytes(((Transformed) segment).source(), seen);
        }
        return total;
    }

    public void append(List<StoredVertexData> vertices) {
        if (vertices.isEmpty()) return;
        add(encode(vertices.size(), sink -> vertices.forEach(v -> sink.vertex(
                v.x(), v.y(), v.z(), v.color().getRGB(), v.u(), v.v(),
                v.normalX(), v.normalY(), v.normalZ()))));
    }

    public void appendTransformed(PackedVertices source, double x, double y, double z, boolean flip) {
        if (source.size() == 0) return;
        // The snapshot contains immutable segments, never the mutable source facade.
        // Later append, self-merge and nested merge retain the eager release semantics.
        add(new Transformed(source.snapshot(), (float) x, (float) y, (float) z, flip ? -1 : 1));
    }

    public void emit(Sink sink) {
        if (first != null) first.emit(sink);
        if (additional != null) for (Segment segment : additional) segment.emit(sink);
    }

    private Snapshot snapshot() {
        if (snapshot == null) {
            Segment[] segments = new Segment[first == null ? 0 : 1 + (additional == null ? 0 : additional.size())];
            if (first != null) segments[0] = first;
            if (additional != null) for (int i = 0; i < additional.size(); i++) segments[i + 1] = additional.get(i);
            snapshot = new Snapshot(size, segments);
        }
        return snapshot;
    }

    private void add(Segment block) {
        int nextSize = Math.addExact(size, block.count());
        if (first == null) first = block;
        else {
            if (additional == null) additional = new ArrayList<>(2);
            additional.add(block);
        }
        size = nextSize;
        snapshot = null;
    }

    private static Block encode(int count, Source source) {
        int bufferSize = Math.min(count, BUFFER_VERTICES) * RECORD_BYTES;
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(Math.min(bufferSize, 4096));
        Deflater deflater = new Deflater(Deflater.BEST_SPEED);
        try (DeflaterOutputStream stream = new DeflaterOutputStream(bytes, deflater,
                Math.max(512, Math.min(bufferSize, 16384)))) {
            class Writer implements Sink {
                final ByteBuffer buffer = ByteBuffer.allocate(bufferSize);
                int written;
                public void vertex(float x, float y, float z, int argb, float u, float v,
                                   float nx, float ny, float nz) {
                    if (buffer.remaining() < RECORD_BYTES) flush();
                    buffer.putInt(Float.floatToRawIntBits(x)).putInt(Float.floatToRawIntBits(y))
                            .putInt(Float.floatToRawIntBits(z)).putInt(argb)
                            .putInt(Float.floatToRawIntBits(u)).putInt(Float.floatToRawIntBits(v))
                            .putInt(Float.floatToRawIntBits(nx)).putInt(Float.floatToRawIntBits(ny))
                            .putInt(Float.floatToRawIntBits(nz));
                    written++;
                }
                void flush() {
                    try { stream.write(buffer.array(), 0, buffer.position()); }
                    catch (IOException error) { throw new UncheckedIOException(error); }
                    buffer.clear();
                }
            }
            Writer writer = new Writer();
            source.emit(writer);
            if (writer.written != count) throw new IllegalStateException("Vertex count changed while packing");
            writer.flush();
        } catch (IOException error) { throw new UncheckedIOException(error); }
        finally { deflater.end(); }
        return intern(count, bytes.toByteArray());
    }

    private static void decode(Block block, Sink sink) {
        byte[] raw = new byte[Math.min(block.count(), BUFFER_VERTICES) * RECORD_BYTES];
        ByteBuffer buffer = ByteBuffer.wrap(raw);
        try (InflaterInputStream stream = new InflaterInputStream(new ByteArrayInputStream(block.bytes()))) {
            int remaining = block.count();
            while (remaining > 0) {
                int count = Math.min(remaining, BUFFER_VERTICES);
                int bytes = count * RECORD_BYTES;
                if (stream.readNBytes(raw, 0, bytes) != bytes) throw new EOFException("Truncated vertex block");
                buffer.clear();
                for (int i = 0; i < count; i++) sink.vertex(
                        Float.intBitsToFloat(buffer.getInt()), Float.intBitsToFloat(buffer.getInt()),
                        Float.intBitsToFloat(buffer.getInt()), buffer.getInt(),
                        Float.intBitsToFloat(buffer.getInt()), Float.intBitsToFloat(buffer.getInt()),
                        Float.intBitsToFloat(buffer.getInt()), Float.intBitsToFloat(buffer.getInt()),
                        Float.intBitsToFloat(buffer.getInt()));
                remaining -= count;
            }
            if (stream.read() != -1) throw new IOException("Unexpected trailing vertex data");
        } catch (IOException error) { throw new UncheckedIOException(error); }
    }
}
