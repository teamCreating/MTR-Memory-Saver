package site.benli06;

import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.zip.ZipFile;
import org.apache.commons.io.IOUtils;
import org.mtr.libraries.com.google.gson.GsonBuilder;

/** Independent source-byte/native-decoder oracle; no String-layout reflection or allocation claims. */
public final class LargeTextWorkspaceAudit {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    private static List<String> entries(Path directory) throws IOException {
        try (var files = Files.list(directory)) {
            return files.map(path -> path.getFileName().toString()).sorted().toList();
        }
    }
    private static final class Observed extends FilterInputStream {
        final Path directory;
        final int chunk, interval;
        long bytes, reads;
        int closeCount;
        boolean sawSnapshot;
        Observed(InputStream input, Path directory, int chunk, int interval) {
            super(input); this.directory = directory; this.chunk = chunk; this.interval = interval;
        }
        @Override public int read(byte[] buffer, int offset, int length) throws IOException {
            int count = in.read(buffer, offset, Math.min(length, chunk));
            if (count > 0) bytes += count;
            if (directory != null && (++reads % interval == 0 || count < 0))
                sawSnapshot |= !entries(directory).isEmpty();
            return count;
        }
        @Override public int read() throws IOException {
            byte[] one = new byte[1]; return read(one, 0, 1) < 0 ? -1 : one[0] & 255;
        }
        @Override public void close() throws IOException { closeCount++; in.close(); }
    }
    private static MessageDigest digest() throws NoSuchAlgorithmException { return MessageDigest.getInstance("SHA-256"); }
    private static String hex(MessageDigest digest) { return HexFormat.of().formatHex(digest.digest()); }
    private static String fileDigest(Path path) throws Exception {
        MessageDigest digest = digest();
        try (var input = new DigestInputStream(Files.newInputStream(path), digest)) {
            input.transferTo(OutputStream.nullOutputStream());
        }
        return hex(digest);
    }
    private static String utf8Digest(String text) throws Exception {
        MessageDigest digest = digest();
        try (var writer = new OutputStreamWriter(new DigestOutputStream(OutputStream.nullOutputStream(), digest), StandardCharsets.UTF_8)) {
            char[] buffer = new char[8192];
            for (int offset = 0; offset < text.length();) {
                int count = Math.min(buffer.length, text.length() - offset);
                text.getChars(offset, offset + count, buffer, 0); writer.write(buffer, 0, count); offset += count;
            }
        }
        return hex(digest);
    }
    private static void clean(ReadAdmission admission, Path directory) throws IOException {
        long[] stats = admission.workspaceStatistics();
        check(admission.active() == 0 && stats[1] == 0 && stats[3] == 0, "Read/workspace admission leaked");
        check(stats[2] <= stats[0], "Logical text payload reservation exceeded its budget");
        check(entries(directory).isEmpty(), "Snapshot file leaked");
    }
    private static Map<String, Object> synthetic(String name, byte[] bytes, Charset charset, Path directory) throws Exception {
        ReadAdmission admission = new ReadAdmission(2, 20000);
        String expected = IOUtils.toString(new ByteArrayInputStream(bytes), charset);
        Observed input = new Observed(new ByteArrayInputStream(bytes), directory, 4000, 1);
        String actual;
        try { actual = SegmentedResourceText.read(input, charset, admission, directory); check(input.closeCount == 0, "Decoder closed caller stream"); }
        finally { input.close(); }
        check(input.closeCount == 1, "Harness did not close the caller stream exactly once");
        check(expected.equals(actual), "Native IOUtils equality failed: " + name);
        check(actual.length() > admission.workspace().share() / 4 && input.sawSnapshot, "Forced-spill control did not observe a snapshot: " + name);
        clean(admission, directory);
        return Map.of("name", name, "charset", charset.name(), "decoded_utf16_units", actual.length(), "native_equal", true,
                "snapshot_observed", input.sawSnapshot, "workspace_statistics", admission.workspaceStatistics());
    }
    private static byte[] append(byte[] prefix, byte[] suffix) {
        byte[] joined = Arrays.copyOf(prefix, prefix.length + suffix.length);
        System.arraycopy(suffix, 0, joined, prefix.length, suffix.length); return joined;
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("Usage: archive entry output");
        Path archive = Path.of(args[0]).toAbsolutePath(), output = Path.of(args[2]).toAbsolutePath();
        Path directory = Files.createTempDirectory("mtr-memory-large-audit-");
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("timestamp", OffsetDateTime.now().toString()); report.put("archive", archive.toString()); report.put("entry", args[1]);
        report.put("java_version", System.getProperty("java.version")); report.put("jvm_arguments", ManagementFactory.getRuntimeMXBean().getInputArguments());
        report.put("max_heap_bytes", Runtime.getRuntime().maxMemory()); report.put("default_max_text_code_units", ReadAdmission.defaultMaxCodeUnits(Runtime.getRuntime().maxMemory()));
        report.put("effective_max_text_code_units", ReadAdmission.GLOBAL.maxCodeUnits()); report.put("temporary_directory", directory.toString());
        report.put("io_utils_source", IOUtils.class.getProtectionDomain().getCodeSource().getLocation().toString());
        report.put("workspace_statistics_order", List.of("budget_bytes", "used_bytes", "peak_bytes", "waiting_requests"));
        Throwable failure = null;
        try {
            report.put("archive_sha256", fileDigest(archive));
            try (var zip = new ZipFile(archive.toFile())) {
                var entry = zip.getEntry(args[1]); check(entry != null && !entry.isDirectory(), "ZIP entry absent or a directory");
                MessageDigest sourceDigest = digest(); long units = 0;
                Observed oracle = new Observed(new DigestInputStream(zip.getInputStream(entry), sourceDigest), null, 8192, 1);
                try (var reader = new InputStreamReader(oracle, StandardCharsets.UTF_8)) {
                    char[] buffer = new char[8192]; for (int count; (count = reader.read(buffer)) != -1;) units += count;
                }
                String sourceSha = hex(sourceDigest); report.put("source_bytes", oracle.bytes); report.put("source_sha256", sourceSha);
                report.put("oracle_decoded_utf16_units", units); report.put("zip_entry_size_bytes", entry.getSize());
                check(oracle.bytes == entry.getSize(), "ZIP payload byte count differed");
                MessageDigest candidateDigest = digest();
                Observed input = new Observed(new DigestInputStream(zip.getInputStream(entry), candidateDigest), directory, 8192, 64);
                String actual;
                try { actual = SegmentedResourceText.read(input, StandardCharsets.UTF_8, ReadAdmission.GLOBAL, directory); check(input.closeCount == 0, "Decoder closed caller stream"); }
                finally { input.close(); }
                report.put("candidate_input_sha256", hex(candidateDigest)); report.put("candidate_input_bytes", input.bytes);
                report.put("candidate_decoded_utf16_units", actual.length()); report.put("candidate_utf8_sha256", utf8Digest(actual));
                report.put("snapshot_observed", input.sawSnapshot); report.put("caller_close_count", input.closeCount);
                check(actual.length() == units && input.bytes == oracle.bytes, "Source/candidate length differed");
                check(sourceSha.equals(report.get("candidate_input_sha256")) && sourceSha.equals(report.get("candidate_utf8_sha256")), "Source/candidate SHA-256 differed");
                check(input.closeCount == 1, "Caller stream close count differed");
                check(4L * units > ReadAdmission.GLOBAL.workspace().share() && input.sawSnapshot, "Large source did not exercise spill path");
                clean(ReadAdmission.GLOBAL, directory);
            }
            List<Map<String, Object>> controls = new ArrayList<>();
            for (String text : List.of("a".repeat(15000), "\u03b1\u4e2d".repeat(7500), "a".repeat(8191) + "\ud83d\ude86\u0000" + "\u4e2d\u03b1".repeat(3500)))
                for (Charset charset : List.of(StandardCharsets.UTF_8, StandardCharsets.UTF_16LE))
                    controls.add(synthetic("text-" + controls.size(), text.getBytes(charset), charset, directory));
            controls.add(synthetic("malformed-utf8-after-spill", append("a".repeat(15000).getBytes(StandardCharsets.UTF_8), new byte[]{(byte)0xc0,(byte)0xaf,(byte)0xe2,(byte)0x82}), StandardCharsets.UTF_8, directory));
            controls.add(synthetic("malformed-utf16le-after-spill", append("a".repeat(15000).getBytes(StandardCharsets.UTF_16LE), new byte[]{0,(byte)0xd8,'z',0,0,(byte)0xdc,1}), StandardCharsets.UTF_16LE, directory));
            report.put("synthetic_controls", controls); report.put("passed", true);
        } catch (Throwable error) {
            failure = error; report.put("passed", false); StringWriter trace = new StringWriter(); error.printStackTrace(new PrintWriter(trace)); report.put("failure", trace.toString());
        } finally {
            report.put("workspace_statistics", ReadAdmission.GLOBAL.workspaceStatistics()); report.put("active_read_scopes", ReadAdmission.GLOBAL.active());
            List<String> remaining = entries(directory); report.put("remaining_snapshot_files", remaining);
            if (remaining.isEmpty()) Files.delete(directory);
            report.put("limits", "Independent streaming UTF-8 source-byte oracle and native IOUtils forced-spill equality; reservation counts cover transient text payloads, excluding fixed buffers, object headers, caller/native retained text, geometry, GPU and process RAM. No full-client acceptance is claimed.");
            Files.writeString(output, new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create().toJson(report), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        }
        if (failure != null) throw new IllegalStateException("Large-text workspace audit failed; see " + output, failure);
        System.out.println("Large-text workspace audit passed: " + output);
    }
}
