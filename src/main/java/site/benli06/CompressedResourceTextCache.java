package site.benli06;

import java.util.function.Function;

/** Native adapter for the independently testable admission/LRU core. */
public final class CompressedResourceTextCache {
    private static final BoundedTextCache CACHE = new BoundedTextCache(
            ReadAdmission.positiveLongProperty("mtr.memory.textCacheBytes", 96L * 1024 * 1024), ReadAdmission.GLOBAL);
    private CompressedResourceTextCache() {}
    public static String get(String key, Function<String, String> reader) { return CACHE.get(key, reader); }
    public static void clear() { CACHE.clear(); }
    public static long[] budgetStatistics() { return CACHE.budgetStatistics(); }
    public static long[] statistics() { return CACHE.statistics(); }
    public static long[] activity() { return CACHE.activity(); }
}
