package site.benli06;

import java.util.HashMap;
import java.util.concurrent.CancellationException;
import org.mtr.MTR;
import org.mtr.core.tool.Utilities;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Vehicle constructors use independent JsonReader maps over generation-scoped trees. */
public final class VehicleJsonCache {
    private static final class Epoch {
        final HashMap<String, JsonObject> values = new HashMap<>();
        boolean retired;
        int requests, unique;
    }
    private static volatile Epoch current = new Epoch();
    private VehicleJsonCache() {}
    public static JsonObject parse(String raw) {
        return parse(raw, ReadAdmission.GLOBAL);
    }
    static JsonObject parse(String raw, ReadAdmission admission) {
        if (raw == null) return Utilities.parseJson(null);
        Epoch epoch = current;
        try (var scope = admission.open(() -> epoch != current)) {
            synchronized (epoch) {
                if (epoch.retired) throw new CancellationException("Vehicle JSON generation retired");
            }
            admission.checkLength(raw.length());
            String key = digest(raw);
            synchronized (epoch) {
                if (epoch.retired) throw new CancellationException("Vehicle JSON generation retired");
                epoch.requests++;
                JsonObject existing = epoch.values.get(key);
                if (existing != null) return existing;
            }
            JsonObject parsed = Utilities.parseJson(raw);
            synchronized (epoch) {
                if (epoch.retired) throw new CancellationException("Vehicle JSON generation retired");
                if (parsed.isEmpty()) return parsed;
                JsonObject existing = epoch.values.putIfAbsent(key, parsed);
                if (existing != null) return existing;
                epoch.unique++;
                return parsed;
            }
        }
    }
    public static synchronized void beginReload() {
        Epoch old = current;
        synchronized (old) { old.retired = true; old.values.clear(); current = new Epoch(); }
    }
    public static synchronized void finishRegistration() {
        Epoch old = current;
        synchronized (old) {
            MTR.LOGGER.info("MTR memory sharing: {} vehicle JSON requests, {} unique nonempty inputs", old.requests, old.unique);
            old.retired = true; old.values.clear(); current = new Epoch();
        }
    }
    private static String digest(String raw) { return ResourceTextDigest.sha256(raw); }
}
