package site.benli06.audit;

import com.sun.management.ThreadMXBean;
import site.benli06.SegmentedResourceText;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.management.ManagementFactory;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.zip.ZipFile;
import org.apache.commons.io.IOUtils;
import org.mtr.libraries.com.google.gson.JsonArray;
import org.mtr.libraries.com.google.gson.JsonObject;

public final class SegmentedResourceTextAudit {
    private static long files, units, synthetic;
    private static volatile String sink;
    private static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
    private static final class Observed extends ByteArrayInputStream {
        boolean closed;
        final int chunk;
        Observed(byte[] input, int chunk) { super(input); this.chunk = chunk; }
        @Override public synchronized int read(byte[] bytes, int offset, int length) {
            return super.read(bytes, offset, Math.min(length, chunk));
        }
        @Override public void close() { closed = true; }
    }
    private static void compare(byte[] bytes, Charset charset, int chunk) throws IOException {
        Observed nativeInput = new Observed(bytes, chunk), candidateInput = new Observed(bytes, chunk);
        String nativeText = IOUtils.toString(nativeInput, charset);
        String candidate = SegmentedResourceText.read(candidateInput, charset);
        check(nativeText.equals(candidate), "Native decoded text differs");
        check(!nativeInput.closed && !candidateInput.closed, "Reader changed native stream ownership");
        synthetic++;
    }
    private static long allocated(byte[] input, boolean candidate, ThreadMXBean counter) throws IOException {
        long thread = Thread.currentThread().threadId(), before = counter.getThreadAllocatedBytes(thread);
        for (int i = 0; i < 3; i++) {
            InputStream stream = new ByteArrayInputStream(input);
            sink = candidate ? SegmentedResourceText.read(stream, StandardCharsets.UTF_8)
                    : IOUtils.toString(stream, StandardCharsets.UTF_8);
        }
        return counter.getThreadAllocatedBytes(thread) - before;
    }
    public static void main(String[] args) throws Exception {
        JsonObject result = new JsonObject();
        for (String text : List.of("", "a", "\ufeffline\r\n车辆\u0000🚆", "a".repeat(8191) + "🚆tail")) {
            for (Charset charset : List.of(StandardCharsets.UTF_8, StandardCharsets.UTF_16BE,
                    StandardCharsets.UTF_16LE, StandardCharsets.ISO_8859_1)) {
                for (int chunk : new int[]{1, 3, 8192}) compare(text.getBytes(charset), charset, chunk);
            }
        }
        compare(new byte[]{(byte)0xef,(byte)0xbb,(byte)0xbf,(byte)0xc0,(byte)0xaf,(byte)0xe2,(byte)0x82}, StandardCharsets.UTF_8, 1);
        compare(new byte[]{(byte)0xff,(byte)0xfe,0,0,(byte)0xd8}, StandardCharsets.UTF_16, 1);
        compare("default charset".getBytes(Charset.defaultCharset()), null, 3);
        try {
            SegmentedResourceText.read(new InputStream() {
                @Override public int read() throws IOException { throw new IOException("expected read failure"); }
            }, StandardCharsets.UTF_8);
            throw new AssertionError("I/O failure hidden");
        } catch (IOException expected) { check(expected.getMessage().equals("expected read failure"), "I/O failure changed"); }
        for (String archive : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
            try (ZipFile zip = new ZipFile(archive)) {
                var entries = zip.entries();
                while (entries.hasMoreElements()) {
                    var entry = entries.nextElement(); String name = entry.getName();
                    if (entry.isDirectory() || !name.startsWith("assets/") ||
                            !(name.endsWith(".json") || name.endsWith(".bbmodel") || name.endsWith(".obj") || name.endsWith(".mtl"))) continue;
                    String baseline, candidate;
                    try (var stream = zip.getInputStream(entry)) { baseline = IOUtils.toString(stream, StandardCharsets.UTF_8); }
                    try (var stream = zip.getInputStream(entry)) { candidate = SegmentedResourceText.read(stream, StandardCharsets.UTF_8); }
                    check(baseline.equals(candidate), "Archive text changed: " + archive + " : " + name);
                    files++; units += baseline.length();
                }
            }
        }
        var counter = (ThreadMXBean) ManagementFactory.getThreadMXBean();
        check(counter.isThreadAllocatedMemorySupported(), "Allocation counters unavailable");
        counter.setThreadAllocatedMemoryEnabled(true);
        JsonArray allocations = new JsonArray();
        for (String text : List.of("model-data\n".repeat(800000), "车辆\n".repeat(1600000))) {
            byte[] input = text.getBytes(StandardCharsets.UTF_8);
            for (int i = 0; i < 3; i++) { sink = IOUtils.toString(new ByteArrayInputStream(input), StandardCharsets.UTF_8); sink = SegmentedResourceText.read(new ByteArrayInputStream(input), StandardCharsets.UTF_8); }
            long original = allocated(input, false, counter), changed = allocated(input, true, counter);
            check(changed < original, "Segmented reader did not reduce this allocation control");
            JsonObject sample = new JsonObject();sample.addProperty("code_units", text.length());
            sample.addProperty("native_allocated_bytes_three_reads", original);sample.addProperty("candidate_allocated_bytes_three_reads", changed);
            allocations.add(sample);
        }
        result.addProperty("passed", true);result.addProperty("real_text_files", files);result.addProperty("input_code_units", units);
        result.addProperty("synthetic_comparisons", synthetic);result.addProperty("native_stream_ownership_preserved", true);
        result.addProperty("io_utils_source", IOUtils.class.getProtectionDomain().getCodeSource().getLocation().toString());
        result.add("allocation_controls", allocations);
        result.addProperty("limits", "Exact native IOUtils text comparison and isolated allocation counters; full-client heap, loading/reload and gameplay acceptance remain separate.");
        Files.writeString(Path.of(args[1]), result.toString(), StandardCharsets.UTF_8);
        System.out.println(result);
    }
}
