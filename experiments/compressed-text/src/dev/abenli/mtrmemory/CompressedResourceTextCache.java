package dev.abenli.mtrmemory;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
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
            char[] chars = new char[length];
            byte[] buffer = new byte[8192];
            int offset = 0, high = -1;
            try (InflaterInputStream stream = new InflaterInputStream(new ByteArrayInputStream(packed))) {
                for (int count; (count = stream.read(buffer)) != -1;) {
                    for (int i = 0; i < count; i++) {
                        if (high < 0) high = buffer[i] & 255;
                        else {
                            if (offset == length) throw new IOException("Resource text length exceeded");
                            chars[offset++] = (char) ((high << 8) | (buffer[i] & 255));
                            high = -1;
                        }
                    }
                }
                if (offset != length || high != -1) throw new IOException("Resource text length mismatch");
                return new String(chars);
            } catch (IOException error) {
                throw new IllegalStateException("Resource text decompression failed", error);
            }
        }
    }

    private static volatile ConcurrentHashMap<String, Text> cache = new ConcurrentHashMap<>();
    private CompressedResourceTextCache() {}

    public static String get(String key, Function<String, String> reader) {
        String[] original = new String[1];
        Text text = cache.computeIfAbsent(key, path -> {
            original[0] = reader.apply(path);
            return original[0] == null ? null : Text.pack(original[0]);
        });
        return text == null ? null : original[0] != null ? original[0] : text.unpack();
    }

    /** Old in-flight readers finish in their old map and cannot publish into a new epoch. */
    public static void clear() { cache = new ConcurrentHashMap<>(); }

    public static long[] statistics() {
        long entries = 0, compressed = 0, codeUnits = 0, packedBytes = 0, rawCodeUnits = 0;
        for (Text text : cache.values()) {
            entries++; codeUnits += text.length();
            if (text.packed() != null) { compressed++; packedBytes += text.packed().length; }
            else rawCodeUnits += text.raw().length();
        }
        return new long[] {entries, compressed, codeUnits, packedBytes, rawCodeUnits};
    }
}
