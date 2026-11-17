package site.benli06;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.mtr.libraries.com.google.gson.GsonBuilder;

/** Actual Windows delete-sharing failure against an unmodified packaged text reader. */
public final class WindowsSnapshotFileLockAudit {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    public static void main(String[] arguments) throws Exception {
        check(System.getProperty("os.name").startsWith("Windows"), "Requires actual Windows filesystem sharing");
        check(arguments.length == 3, "Supply fresh audit directory, lock helper and JSON output");
        Path directory = Path.of(arguments[0]).toAbsolutePath(), helper = Path.of(arguments[1]).toAbsolutePath();
        Path output = Path.of(arguments[2]).toAbsolutePath();
        Files.createDirectory(directory);
        Path snapshots = Files.createDirectory(directory.resolve("snapshots"));
        Path ready = directory.resolve("lock-ready.json"), release = directory.resolve("release-lock");
        var admission = new ReadAdmission(2, 20000);
        String expected = "a".repeat(15000) + "🚆\u0000\u03b1";
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("timestamp", OffsetDateTime.now().toString());
        report.put("reader_code_source", SegmentedResourceText.class.getProtectionDomain().getCodeSource().getLocation().toString());
        report.put("java_version", System.getProperty("java.version"));
        report.put("os_name", System.getProperty("os.name"));
        final Process[] lock = {null}; final Path[] snapshot = {null};
        Throwable failure = null;
        try {
            var input = new ByteArrayInputStream(expected.getBytes(StandardCharsets.UTF_8)) {
                @Override public synchronized int read(byte[] bytes, int offset, int length) {
                    try {
                        if (lock[0] == null) {
                            try (var files = Files.list(snapshots)) { snapshot[0] = files.findFirst().orElse(null); }
                            if (snapshot[0] != null) {
                                lock[0] = new ProcessBuilder("pwsh", "-NoProfile", "-File", helper.toString(),
                                        "-Snapshot", snapshot[0].toString(), "-Ready", ready.toString(), "-Release", release.toString())
                                        .redirectOutput(directory.resolve("lock.stdout.log").toFile())
                                        .redirectError(directory.resolve("lock.stderr.log").toFile()).start();
                                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
                                while (!Files.exists(ready)) {
                                    check(lock[0].isAlive(), "Lock helper exited before acquiring the handle");
                                    check(System.nanoTime() < deadline, "Lock acquisition was not confirmed");
                                    Thread.sleep(20);
                                }
                            }
                        }
                        return super.read(bytes, offset, Math.min(length, 4000));
                    } catch (Exception error) { throw new IllegalStateException("Could not establish actual Windows snapshot lock", error); }
                }
            };
            IOException deletion = null;
            try { SegmentedResourceText.read(input, StandardCharsets.UTF_8, admission, snapshots); }
            catch (IOException error) { deletion = error; }
            check(lock[0] != null && Files.exists(ready), "No real lock was observed");
            check(deletion instanceof AccessDeniedException || deletion instanceof FileSystemException,
                    "Reader did not report an actual filesystem deletion failure");
            check(Files.exists(snapshot[0]), "Failed deletion cannot be reported as successful cleanup");
            check(Files.size(snapshot[0]) == 2L * expected.length(), "Snapshot bytes are incomplete");
            check(admission.active() == 0 && admission.workspaceStatistics()[1] == 0 && admission.workspaceStatistics()[3] == 0,
                    "Failed deletion leaked a read scope or text reservation");
            report.put("lock_pid", lock[0].pid());
            report.put("deletion_error_type", deletion.getClass().getName());
            report.put("deletion_error", deletion.toString());
            report.put("snapshot_retained_on_error", true);
            report.put("snapshot_bytes_on_error", Files.size(snapshot[0]));
            report.put("workspace_statistics", admission.workspaceStatistics());
            Files.writeString(release, "Release the fixture-owned file handle", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
            check(lock[0].waitFor(15, TimeUnit.SECONDS), "Actual lock process did not exit");
            check(lock[0].exitValue() == 0, "Lock process exited unsuccessfully");
            report.put("lock_exit_code", lock[0].exitValue());
            Files.delete(snapshot[0]);
            report.put("fixture_cleanup_after_unlock", true);
            report.put("passed", true);
        } catch (Throwable error) {
            failure = error; report.put("passed", false); report.put("failure", error.toString());
        } finally {
            if (lock[0] != null && lock[0].isAlive()) {
                if (!Files.exists(release)) Files.writeString(release, "Release on audit failure", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
                report.put("cleanup_lock_exit_confirmed", lock[0].waitFor(15, TimeUnit.SECONDS));
            }
            report.put("active_read_scopes", admission.active());
            try (var files = Files.list(snapshots)) {
                report.put("remaining_snapshot_files", files.map(path -> path.getFileName().toString()).toList());
            }
            report.put("limits", "An actual Windows file handle rejects snapshot deletion. The reader reports failure and settles memory ownership. Explicit fixture cleanup after handle release is not automatic product recovery. Disk-full, output flush and abrupt process-exit recovery are separate observations.");
            Files.writeString(output, new GsonBuilder().setPrettyPrinting().create().toJson(report), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        }
        if (failure != null) throw new IllegalStateException("Windows snapshot audit failed; see " + output, failure);
        System.out.println("Windows snapshot file-lock audit passed: " + output);
    }
}
