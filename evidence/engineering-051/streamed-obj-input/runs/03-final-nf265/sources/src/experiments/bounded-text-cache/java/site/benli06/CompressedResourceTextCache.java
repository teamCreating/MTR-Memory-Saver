package site.benli06;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.InflaterInputStream;

/** Stores exact UTF-16 code units without retaining large source Strings. */
public final class CompressedResourceTextCache {
    private record Text(String raw, byte[] packed, int length) {
        static Text pack(String value) {
            if (value.isEmpty()) return new Text(value, null, 0);
            Deflater deflater = new Deflater(Deflater.BEST_SPEED);
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try {
                try (DeflaterOutputStream stream = new DeflaterOutputStream(bytes, deflater)) {
                    byte[] buffer = new byte[8192];
                    for (int offset = 0; offset < value.length();) {
                        int chars = Math.min(buffer.length / 2, value.length() - offset);
                        for (int i = 0; i < chars; i++) {
                            char c = value.charAt(offset + i);
                            buffer[2 * i] = (byte) (c >>> 8);
                            buffer[2 * i + 1] = (byte) c;
                        }
                        stream.write(buffer, 0, chars * 2);
                        offset += chars;
                    }
                }
                byte[] packed = bytes.toByteArray();
                // A Java String needs at least one payload byte per code unit.
                return packed.length < value.length() ? new Text(null, packed, value.length())
                        : new Text(value, null, value.length());
            } catch (IOException error) {
                throw new IllegalStateException("Resource text compression failed", error);
            } finally { deflater.end(); }
        }

        String unpack() {
            if (raw != null) return raw;
            // Bound the temporary UTF-16 buffer; segments preserve arbitrary code
            // units, including unpaired surrogates and pairs split at a boundary.
            char[] chars = new char[Math.min(length, 4096)];
            List<String> segments = length > chars.length ? new ArrayList<>() : null;
            byte[] buffer = new byte[8192];
            int offset = 0, used = 0, high = -1;
            try (InflaterInputStream stream = new InflaterInputStream(new ByteArrayInputStream(packed))) {
                for (int count; (count = stream.read(buffer)) != -1;) {
                    int i = 0;
                    if (high >= 0 && count != 0) {
                        if (offset == length) throw new IOException("Resource text length exceeded");
                        chars[used++] = (char) ((high << 8) | (buffer[i++] & 255));
                        offset++;
                        high = -1;
                    }
                    for (; i + 1 < count; i += 2) {
                        if (offset == length) throw new IOException("Resource text length exceeded");
                        chars[used++] = (char) (((buffer[i] & 255) << 8) | (buffer[i + 1] & 255));
                        offset++;
                    }
                    if (i < count) high = buffer[i] & 255;
                    // At most 4096 complete code units arrive in an 8192-byte
                    // read, including a high byte carried from the previous read.
                    if (segments != null && used != 0) {
                        segments.add(new String(chars, 0, used));
                        used = 0;
                    }
                }
                if (offset != length || high != -1) throw new IOException("Resource text length mismatch");
                if (segments == null) return new String(chars);
                if (used != 0) segments.add(new String(chars, 0, used));
                return String.join("", segments);
            } catch (IOException error) {
                throw new IllegalStateException("Resource text decompression failed", error);
            }
        }
    }

    // Reserve most of the heap for native parsing and live model data. The limit
    // counts conservative payload/key weights, not an exact JVM object census.
    private static final long BUDGET = Math.max(0, Long.getLong(
            "mtr.memory.resourceTextCacheBytes", Runtime.getRuntime().maxMemory() / 32));

    private static final class Epoch {
        final ConcurrentHashMap<String, Text> values = new ConcurrentHashMap<>();
        final java.util.LinkedHashMap<String, Text> recent = new java.util.LinkedHashMap<>(16, .75f, true);
        long retainedWeight;
        long peakWeight;
        long evictions;

        synchronized void accessed(String key, Text text) {
            // A concurrent eviction may already have removed this exact entry.
            if (values.get(key) != text) return;
            if (recent.get(key) != null) return;
            long weight = weight(key, text);
            if (weight > BUDGET) {
                values.remove(key, text);
                evictions++;
                return;
            }
            var iterator = recent.entrySet().iterator();
            while (retainedWeight + weight > BUDGET && iterator.hasNext()) {
                var oldest = iterator.next();
                values.remove(oldest.getKey(), oldest.getValue());
                retainedWeight -= weight(oldest.getKey(), oldest.getValue());
                iterator.remove();
                evictions++;
            }
            recent.put(key, text);
            retainedWeight += weight;
            peakWeight = Math.max(peakWeight, retainedWeight);
        }

        synchronized long[] budgetStatistics() {
            return new long[] {BUDGET, retainedWeight, peakWeight, evictions};
        }
    }

    private static long weight(String key, Text text) {
        return 192L + 2L * key.length() + (text.packed() == null
                ? 2L * text.length() : text.packed().length);
    }

    private static volatile Epoch cache = new Epoch();
    private CompressedResourceTextCache() {}

    public static String get(String key, Function<String, String> reader) {
        Epoch epoch = cache;
        String[] original = new String[1];
        Text text = epoch.values.computeIfAbsent(key, path -> {
            original[0] = reader.apply(path);
            return original[0] == null ? null : Text.pack(original[0]);
        });
        if (text != null) epoch.accessed(key, text);
        return text == null ? null : original[0] != null ? original[0] : text.unpack();
    }

    /** Old in-flight readers finish in their old map and cannot publish into a new epoch. */
    public static void clear() { cache = new Epoch(); }

    /** Budget, current/peak admitted weight, and eviction count for this epoch. */
    public static long[] budgetStatistics() { return cache.budgetStatistics(); }

    public static long[] statistics() {
        long entries = 0, compressed = 0, codeUnits = 0, packedBytes = 0, rawCodeUnits = 0;
        for (Text text : cache.values.values()) {
            entries++; codeUnits += text.length();
            if (text.packed() != null) { compressed++; packedBytes += text.packed().length; }
            else rawCodeUnits += text.raw().length();
        }
        return new long[] {entries, compressed, codeUnits, packedBytes, rawCodeUnits};
    }
}
