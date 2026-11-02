package dev.abenli.mtrmemory;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.mtr.MTR;
import org.mtr.core.tool.Utilities;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Vehicle constructors read these trees through independent JsonReader maps. */
public final class VehicleJsonCache {
    private static final ConcurrentHashMap<String, JsonObject> CACHE = new ConcurrentHashMap<>();
    private static final AtomicInteger REQUESTS = new AtomicInteger();
    private static final AtomicInteger UNIQUE = new AtomicInteger();
    private VehicleJsonCache() {}

    public static JsonObject parse(String raw) {
        // Preserve the release's null/malformed/empty handling and repeated diagnostics.
        if (raw == null) return Utilities.parseJson(null);
        REQUESTS.incrementAndGet();
        String key = digest(raw);
        JsonObject existing = CACHE.get(key);
        if (existing != null) return existing;
        JsonObject parsed = Utilities.parseJson(raw);
        if (parsed.isEmpty()) return parsed;
        existing = CACHE.putIfAbsent(key, parsed);
        if (existing != null) return existing;
        UNIQUE.incrementAndGet();
        return parsed;
    }

    public static void beginReload() {
        CACHE.clear();
        REQUESTS.set(0);
        UNIQUE.set(0);
    }

    public static void finishRegistration() {
        MTR.LOGGER.info("MTR memory sharing: {} vehicle JSON requests, {} unique nonempty inputs",
                REQUESTS.get(), UNIQUE.get());
        // Readers retain required children; later requests can parse resource text again.
        CACHE.clear();
    }

    private static String digest(String raw) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(raw.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }
}
