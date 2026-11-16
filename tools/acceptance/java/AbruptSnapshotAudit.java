package site.benli06;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.mtr.libraries.com.google.gson.GsonBuilder;

/** Child JVM audit of the packaged public reader; only audit-owned files are touched. */
public final class AbruptSnapshotAudit {
    private static final String TEXT = "a".repeat(15000) + "\ud83d\ude86\u0000\u03b1";
    private static final int HALT_CODE = 74;

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    private static List<Path> entries(Path directory) throws IOException {
        try (var files = Files.list(directory)) { return files.sorted().toList(); }
    }
    private static void json(Path path, Object value) throws IOException {
        Path temporary = path.resolveSibling(path.getFileName() + ".tmp");
        Files.writeString(temporary, new GsonBuilder().setPrettyPrinting().create().toJson(value) + "\n",
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE);
    }

    public static void main(String[] args) throws Exception {
        check(args.length == 2, "Usage: halt|normal output-directory");
        check(args[0].equals("halt") || args[0].equals("normal"), "Unknown audit mode");
        String mode = args[0];
        Path output = Path.of(args[1]).toAbsolutePath();
        Path temporary = Path.of(System.getProperty("java.io.tmpdir")).toAbsolutePath();
        check(Files.isDirectory(output) && Files.isDirectory(temporary), "Require prepared owned directories");
        List<Path> prior = entries(temporary);
        var admission = new ReadAdmission(2, 20000);
        var process = ProcessHandle.current();
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try { Files.writeString(output.resolve("shutdown-hook-ran"), Instant.now().toString(), StandardOpenOption.CREATE_NEW); }
            catch (IOException failure) { throw new java.io.UncheckedIOException(failure); }
        }, "audit-shutdown-marker"));

        final boolean[] observed = {false};
        final int[] closes = {0};
        ByteArrayInputStream input = new ByteArrayInputStream(TEXT.getBytes(StandardCharsets.UTF_8)) {
            @Override public synchronized int read(byte[] bytes, int offset, int length) {
                try {
                    if (!observed[0]) {
                        var fresh = new ArrayList<>(entries(temporary));
                        fresh.removeAll(prior);
                        if (!fresh.isEmpty() && Files.size(fresh.getFirst()) > 0) {
                            check(fresh.size() == 1, "More than one new snapshot exists");
                            Path snapshot = fresh.getFirst();
                            check(snapshot.getFileName().toString().startsWith("mtr-memory-text-"), "Unexpected spill file name");
                            check(admission.active() == 1, "Reader was not active when spill was observed");
                            Map<String, Object> ready = new LinkedHashMap<>();
                            ready.put("timestamp", Instant.now().toString());
                            ready.put("pid", process.pid());
                            ready.put("process_created", process.info().startInstant().orElseThrow().toString());
                            ready.put("mode", mode);
                            ready.put("snapshot", snapshot.toString());
                            ready.put("snapshot_bytes", Files.size(snapshot));
                            ready.put("active_read_scopes", admission.active());
                            ready.put("workspace_statistics", admission.workspaceStatistics());
                            ready.put("reader_code_source", SegmentedResourceText.class.getProtectionDomain().getCodeSource().getLocation().toString());
                            ready.put("admission_code_source", ReadAdmission.class.getProtectionDomain().getCodeSource().getLocation().toString());
                            json(output.resolve("spill-ready.json"), ready);
                            observed[0] = true;
                            if (mode.equals("halt")) {
                                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);
                                while (!Files.exists(output.resolve("halt-after-observation"))) {
                                    check(System.nanoTime() < deadline, "Parent did not confirm actual spill before halt");
                                    Thread.sleep(10);
                                }
                                Runtime.getRuntime().halt(HALT_CODE);
                                throw new AssertionError("Runtime.halt returned");
                            }
                        }
                    }
                    return super.read(bytes, offset, Math.min(length, 4000));
                } catch (IOException failure) { throw new java.io.UncheckedIOException(failure); }
                catch (InterruptedException failure) { Thread.currentThread().interrupt(); throw new IllegalStateException(failure); }
            }
            @Override public void close() throws IOException {
                closes[0]++;
                Files.writeString(output.resolve("caller-stream-closed"), Integer.toString(closes[0]));
                super.close();
            }
        };
        String actual;
        try {
            actual = SegmentedResourceText.read(input, StandardCharsets.UTF_8, admission);
            check(closes[0] == 0, "Packaged reader closed its caller stream");
        } finally { input.close(); }
        check(mode.equals("normal"), "Halt mode completed normally without exercising abrupt exit");
        check(observed[0], "No real spilled bytes observed");
        check(TEXT.equals(actual), "Decoded text differs");
        check(entries(temporary).equals(prior), "Normal completion left a new file or changed entry ownership");
        check(admission.active() == 0 && admission.workspaceStatistics()[1] == 0 && admission.workspaceStatistics()[3] == 0,
                "Normal completion leaked admission ownership");
        json(output.resolve("result.json"), Map.of("passed", true, "pid", process.pid(),
                "decoded_units", actual.length(), "caller_closes", closes[0], "active_reads", admission.active(),
                "workspace_statistics", admission.workspaceStatistics(), "existing_entries_preserved", prior.stream().map(Path::toString).toList()));
    }
}
