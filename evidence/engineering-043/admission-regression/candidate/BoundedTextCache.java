package site.benli06;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.function.Function;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.InflaterInputStream;

/** Exact UTF-16 LRU, admitted before insertion; readers and unpackers share admission. */
public final class BoundedTextCache {
    private record Text(String raw, byte[] packed, int length) {
        long weight(String key) { return 192L + 2L * key.length() + (packed == null ? 2L * length : packed.length); }
        static Text raw(String raw) { return raw == null ? null : new Text(raw, null, raw.length()); }
        static Text pack(String value) {
            if (value.isEmpty()) return raw(value);
            Deflater deflater = new Deflater(Deflater.BEST_SPEED);
            ByteArrayOutputStream output = new ByteArrayOutputStream(Math.min(value.length(), 8192));
            // Stop before allocating output that cannot beat compact String storage.
            OutputStream bounded = new OutputStream() {
                @Override public void write(int b) { if (output.size() + 1 >= value.length()) throw new NoGain(); output.write(b); }
                @Override public void write(byte[] b, int off, int count) {
                    if ((long) output.size() + count >= value.length()) throw new NoGain();
                    output.write(b, off, count);
                }
            };
            try (DeflaterOutputStream stream = new DeflaterOutputStream(bounded, deflater)) {
                byte[] buffer = new byte[8192];
                for (int offset = 0; offset < value.length();) {
                    if (Thread.currentThread().isInterrupted()) throw new CancellationException("Compression interrupted");
                    int count = Math.min(buffer.length / 2, value.length() - offset);
                    for (int i = 0; i < count; i++) {
                        char c = value.charAt(offset + i);
                        buffer[2 * i] = (byte) (c >>> 8);
                        buffer[2 * i + 1] = (byte) c;
                    }
                    stream.write(buffer, 0, count * 2);
                    offset += count;
                }
                stream.finish();
                return new Text(null, output.toByteArray(), value.length());
            } catch (NoGain ignored) { return raw(value); }
            catch (IOException error) { throw new IllegalStateException("Resource compression failed", error); }
            finally { deflater.end(); }
        }
        String unpack(ReadAdmission admission) {
            if (raw != null) return raw;
            admission.checkLength(length);
            char[] chars = new char[4096];
            var segments = new ArrayList<String>();
            int used = 0, total = 0;
            try (var stream = new InflaterInputStream(new ByteArrayInputStream(packed))) {
                byte[] bytes = new byte[8192];
                int high = -1;
                for (int count; (count = stream.read(bytes)) != -1;) {
                    admission.checkLength(total);
                    for (int i = 0; i < count; i++) {
                        int b = bytes[i] & 255;
                        if (high < 0) high = b;
                        else {
                            if (++total > length) throw new IOException("Resource text length exceeded");
                            chars[used++] = (char) ((high << 8) | b); high = -1;
                            if (used == chars.length) { segments.add(new String(chars)); used = 0; }
                        }
                    }
                }
                if (high >= 0 || total != length) throw new IOException("Resource text length mismatch");
            } catch (IOException error) { throw new IllegalStateException("Resource decompression failed", error); }
            if (used > 0) segments.add(new String(chars, 0, used));
            return String.join("", segments);
        }
    }
    private static final class NoGain extends RuntimeException {}
    private record Pending(Thread owner, CompletableFuture<Text> ready) {}
    private static final class Epoch {
        final LinkedHashMap<String, Text> values = new LinkedHashMap<>(16, .75f, true);
        final Map<String, Pending> pending = new HashMap<>();
        boolean retired;
        long weight, peak, evictions, reads, hits, unpacks, compressionAttempts, bypasses, failures;
    }
    private final long budget;
    private final ReadAdmission admission;
    private volatile Epoch current = new Epoch();
    public BoundedTextCache(long budget, ReadAdmission admission) {
        if (budget < 1) throw new IllegalArgumentException("Text cache budget must be positive");
        this.budget = budget; this.admission = admission;
    }
    public String get(String key, Function<String, String> reader) {
        Epoch epoch = current;
        try (var scope = admission.open(() -> epoch != current)) {
            Pending pending;
            boolean owner;
            Text hit;
            synchronized (epoch) {
                if (epoch.retired) throw new CancellationException("Resource generation retired");
                hit = epoch.values.get(key);
                if (hit != null) { epoch.hits++; if (hit.packed != null) epoch.unpacks++; }
                pending = epoch.pending.get(key);
                owner = pending == null;
                if (hit == null && owner) {
                    pending = new Pending(Thread.currentThread(), new CompletableFuture<>());
                    epoch.pending.put(key, pending); epoch.reads++;
                } else if (hit == null && pending.owner == Thread.currentThread()) {
                    throw new IllegalStateException("Recursive resource read: " + key);
                }
            }
            if (hit != null) return restore(hit, epoch);
            if (!owner) return restore(await(pending.ready), epoch);
            try {
                String raw = reader.apply(key);
                if (raw != null) admission.checkLength(raw.length());
                Text text = Text.raw(raw);
                boolean cacheable = text != null && text.weight(key) <= budget;
                synchronized (epoch) { if (cacheable) epoch.compressionAttempts++; else epoch.bypasses++; }
                if (cacheable) text = Text.pack(raw);
                synchronized (epoch) {
                    if (epoch.retired) throw new CancellationException("Resource generation retired");
                    if (cacheable) {
                        long weight = text.weight(key);
                        var oldest = epoch.values.entrySet().iterator();
                        while (epoch.weight + weight > budget && oldest.hasNext()) {
                            var entry = oldest.next();
                            epoch.weight -= entry.getValue().weight(entry.getKey());
                            oldest.remove(); epoch.evictions++;
                        }
                        epoch.values.put(key, text); epoch.weight += weight;
                        epoch.peak = Math.max(epoch.peak, epoch.weight);
                    }
                    pending.ready.complete(text);
                }
                return raw; // Preserve the initial reader's String identity.
            } catch (Throwable error) {
                synchronized (epoch) { epoch.failures++; }
                pending.ready.completeExceptionally(error);
                throw error;
            } finally { synchronized (epoch) { epoch.pending.remove(key, pending); } }
        }
    }
    private String restore(Text text, Epoch epoch) {
        String value = text == null ? null : text.unpack(admission);
        synchronized (epoch) {
            if (epoch.retired) throw new CancellationException("Resource generation retired");
            return value;
        }
    }
    private static Text await(CompletableFuture<Text> ready) {
        try { return ready.get(); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new CancellationException("Resource wait interrupted"); }
        catch (java.util.concurrent.ExecutionException error) { throw new CompletionException(error.getCause()); }
    }
    public void clear() {
        Epoch old;
        synchronized (this) {
            old = current;
            synchronized (old) {
                old.retired = true;
                current = new Epoch();
                old.values.clear(); old.weight = 0;
                old.pending.values().forEach(entry -> entry.ready.cancel(false)); old.pending.clear();
            }
        }
    }
    public long[] budgetStatistics() {
        Epoch epoch = current;
        synchronized (epoch) { return new long[] {budget, epoch.weight, epoch.peak, epoch.evictions}; }
    }
    public long[] statistics() {
        Epoch epoch = current;
        synchronized (epoch) {
            long compressed = 0, codeUnits = 0, packedBytes = 0, rawUnits = 0;
            for (Text text : epoch.values.values()) {
                codeUnits += text.length;
                if (text.packed != null) { compressed++; packedBytes += text.packed.length; }
                else rawUnits += text.length;
            }
            return new long[] {epoch.values.size(), compressed, codeUnits, packedBytes, rawUnits};
        }
    }
    /** Reads, hits, unpacks, compression attempts, bypasses, failures, pending readers. */
    public long[] activity() {
        Epoch epoch = current;
        synchronized (epoch) { return new long[] {epoch.reads, epoch.hits, epoch.unpacks, epoch.compressionAttempts,
                epoch.bypasses, epoch.failures, epoch.pending.size()}; }
    }
}
