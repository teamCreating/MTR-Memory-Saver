package site.benli06.audit;

import com.sun.management.ThreadMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Method;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.zip.ZipFile;
import site.benli06.GenerationWorkCache;
import site.benli06.ReadAdmission;

/** Text/source-key microbenchmark. A digest stands in for a parsed model; no native parse/GPU. */
public final class SourceLookupBenchmark {
    private static long allocations(ThreadMXBean bean, Map<Long, Long> before) {
        long total = 0;
        for (long id : bean.getAllThreadIds()) {
            long value = bean.getThreadAllocatedBytes(id);
            if (value >= 0) total += Math.max(0, value - before.getOrDefault(id, 0L));
        }
        return total;
    }
    public static void main(String[] args) throws Exception {
        String mode = args[0];
        Path measuredJar = Path.of(args[1]);
        List<String> jobs = Files.readAllLines(Path.of(args[2]), StandardCharsets.UTF_8);
        int epochs = Integer.parseInt(args[3]), queries = Integer.parseInt(args[4]);
        Path output = Path.of(args[5]);
        if (Files.exists(output) || epochs < 1 || queries < 1 || jobs.isEmpty()) throw new IllegalArgumentException("Use fresh output and positive nonempty workload");
        boolean candidate = mode.equals("candidate");
        if (!candidate && !mode.equals("baseline")) throw new IllegalArgumentException("Unknown benchmark mode");
        var bean = (ThreadMXBean) ManagementFactory.getThreadMXBean();
        if (!bean.isThreadAllocatedMemorySupported()) throw new IllegalStateException("Allocation counters unavailable");
        bean.setThreadAllocatedMemoryEnabled(true);
        try (var isolated = new URLClassLoader(new java.net.URL[] {measuredJar.toUri().toURL()}, ClassLoader.getPlatformClassLoader());
             var sources = new GenerationWorkCache<String, String, String>(2, 64, Duration.ofMinutes(5),
                     new ReadAdmission(2, Runtime.getRuntime().maxMemory() / 32), () -> {}, () -> {})) {
            Method textGet = isolated.loadClass("site.benli06.CompressedResourceTextCache").getMethod("get", String.class, java.util.function.Function.class);
            Method clear = isolated.loadClass("site.benli06.CompressedResourceTextCache").getMethod("clear");
            Method reader = isolated.loadClass("site.benli06.SegmentedResourceText").getMethod("read", java.io.InputStream.class, java.nio.charset.Charset.class);
            Method digest = isolated.loadClass("site.benli06.ResourceTextDigest").getMethod("sha256", String.class);
            Map<String, ZipFile> archives = new HashMap<>();
            for (String job : jobs) {
                String archive = job.split("\t", -1)[0];
                if (!archives.containsKey(archive)) archives.put(archive, new ZipFile(archive));
            }
            try {
                String warm = "warmup-data".repeat(1000);
                for (int i = 0; i < 20; i++) { textGet.invoke(null, "warm", (java.util.function.Function<String, String>) ignored -> warm); digest.invoke(null, warm); }
                if (candidate) sources.get("warm", () -> new GenerationWorkCache.Prepared<>("warm", () -> "warm")).get();
                clear.invoke(null); sources.beginReload(); System.gc();
                AtomicLong reads = new AtomicLong(), hashes = new AtomicLong(), peak = new AtomicLong(), samples = new AtomicLong();
                AtomicBoolean observing = new AtomicBoolean(true);
                Thread observer = new Thread(() -> {
                    while (observing.get()) {
                        peak.accumulateAndGet(ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(), Math::max);
                        samples.incrementAndGet();
                        try { Thread.sleep(10); } catch (InterruptedException ignored) { return; }
                    }
                }, "benchmark-heap-observer");
                observer.setDaemon(true); observer.start();
                Map<Long, Long> before = new HashMap<>();
                for (long id : bean.getAllThreadIds()) before.put(id, Math.max(0, bean.getThreadAllocatedBytes(id)));
                long gcBefore = 0, gcTimeBefore = 0;
                for (var gc : ManagementFactory.getGarbageCollectorMXBeans()) { gcBefore += gc.getCollectionCount(); gcTimeBefore += gc.getCollectionTime(); }
                Map<String, String> oldSources = new HashMap<>();
                var resultDigest = java.security.MessageDigest.getInstance("SHA-256");
                Instant start = Instant.now(); long startNanos = System.nanoTime();
                for (int epoch = 0; epoch < epochs; epoch++) {
                    clear.invoke(null); sources.beginReload(); oldSources.clear();
                    for (int query = 0; query < queries; query++) for (int index = 0; index < jobs.size(); index++) {
                        String[] job = jobs.get(index).split("\t", -1);
                        String key = Integer.toString(index);
                        java.util.function.Supplier<String> text = () -> {
                            try {
                                return (String) textGet.invoke(null, key, (java.util.function.Function<String, String>) ignored -> {
                                    reads.incrementAndGet();
                                    try (var stream = archives.get(job[0]).getInputStream(archives.get(job[0]).getEntry(job[1]))) {
                                        return (String) reader.invoke(null, stream, StandardCharsets.UTF_8);
                                    } catch (Exception error) { throw new java.util.concurrent.CompletionException(error); }
                                });
                            } catch (Exception error) { throw new java.util.concurrent.CompletionException(error); }
                        };
                        java.util.function.Supplier<String> hash = () -> {
                            try { String raw = text.get(); hashes.incrementAndGet(); return (String) digest.invoke(null, raw); }
                            catch (Exception error) { throw new java.util.concurrent.CompletionException(error); }
                        };
                        String result;
                        if (candidate) result = sources.get(key, () -> {
                            String value = hash.get();
                            return new GenerationWorkCache.Prepared<>(value, () -> value);
                        }).get();
                        else { String value = hash.get(); result = oldSources.computeIfAbsent(value, ignored -> value); }
                        resultDigest.update(result.getBytes(StandardCharsets.US_ASCII));
                    }
                }
                long elapsed = System.nanoTime() - startNanos; Instant end = Instant.now();
                long allocated = allocations(bean, before), gcAfter = 0, gcTimeAfter = 0;
                for (var gc : ManagementFactory.getGarbageCollectorMXBeans()) { gcAfter += gc.getCollectionCount(); gcTimeAfter += gc.getCollectionTime(); }
                observing.set(false); observer.interrupt(); observer.join();
                sources.finishRegistration(); clear.invoke(null); oldSources.clear(); System.gc();
                long retained = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
                String report = "{\"mode\":\"" + mode + "\",\"start\":\"" + start + "\",\"end\":\"" + end
                        + "\",\"elapsed_ms\":" + elapsed / 1e6 + ",\"allocated_bytes_live_threads\":" + allocated
                        + ",\"resource_reads\":" + reads + ",\"digest_calls\":" + hashes + ",\"gc_count\":" + (gcAfter - gcBefore)
                        + ",\"gc_collection_ms\":" + (gcTimeAfter - gcTimeBefore) + ",\"sampled_peak_heap_bytes\":" + peak
                        + ",\"heap_samples\":" + samples + ",\"post_release_full_gc_heap_bytes\":" + retained
                        + ",\"max_heap_bytes\":" + Runtime.getRuntime().maxMemory() + ",\"result_sha256\":\""
                        + java.util.HexFormat.of().formatHex(resultDigest.digest()) + "\"}";
                Files.writeString(output, report + "\n", StandardCharsets.UTF_8); System.out.println(report);
            } finally { for (ZipFile archive : archives.values()) archive.close(); }
        }
    }
}
