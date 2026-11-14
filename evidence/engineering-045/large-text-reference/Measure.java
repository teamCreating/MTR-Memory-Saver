import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;

/** Constant-memory exact Java UTF-8 decoding measurements of pinned ZIP inputs. */
public final class Measure {
    private static final String[] COMMANDS = {"v", "vt", "vn", "f", "g", "o", "usemtl", "mtllib"};
    private static final class Metrics {
        long units, utf8Bytes, nonLatin1, supplementary, replacements, lines;
        char pendingHigh;
        final long[] commands = new long[COMMANDS.length];
        final char[] token = new char[12];
        int tokenLength;
        boolean tokenDone;
        final boolean obj;
        Metrics(boolean obj) { this.obj = obj; }
        void command() {
            if (obj && !tokenDone && tokenLength > 0 && tokenLength <= token.length) {
                String value = new String(token, 0, tokenLength);
                for (int i = 0; i < COMMANDS.length; i++) if (COMMANDS[i].equals(value)) commands[i]++;
            }
            tokenDone = true;
        }
        void accept(char value) {
            units++;
            if (value > 255) nonLatin1++;
            if (value == 0xfffd) replacements++;
            if (pendingHigh != 0) {
                if (Character.isLowSurrogate(value)) {
                    utf8Bytes += 4;
                    supplementary++;
                    pendingHigh = 0;
                    return;
                }
                utf8Bytes++;
                pendingHigh = 0;
            }
            if (Character.isHighSurrogate(value)) pendingHigh = value;
            else if (Character.isLowSurrogate(value)) utf8Bytes++;
            else utf8Bytes += value < 0x80 ? 1 : value < 0x800 ? 2 : 3;
            if (value == '\n') {
                lines++;
                command(); tokenLength = 0; tokenDone = false;
            } else if (obj && !tokenDone) {
                if (value <= ' ') { if (tokenLength > 0) command(); }
                else { if (tokenLength < token.length) token[tokenLength] = value; tokenLength++; }
            }
        }
        void finish() { if (pendingHigh != 0) utf8Bytes++; command(); }
    }
    public static void main(String[] args) throws Exception {
        var rows = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        try (var output = Files.newBufferedWriter(Path.of(args[1]), StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW)) {
            output.write("source_index\tkind\tresource\tzip_bytes\tdecoded_utf16_units\treencoded_utf8_bytes\tcompact_coder\tcompact_payload_bytes\tnon_latin1_units\tsupplementary_pairs\treplacement_units\tlf_count\tsha256\tobj_directive_counts\n");
            int count = 0;
            for (String line : rows) {
                var parts = line.split("\t", -1);
                try (var zip = new ZipFile(parts[2])) {
                    var entry = zip.getEntry(parts[3]);
                    if (entry == null) throw new IOException("Pinned entry disappeared: " + parts[3]);
                    var hash = MessageDigest.getInstance("SHA-256");
                    var metrics = new Metrics(parts[1].equals("obj"));
                    try (var input = new DigestInputStream(zip.getInputStream(entry), hash);
                         var reader = new InputStreamReader(input, StandardCharsets.UTF_8)) {
                        char[] buffer = new char[8192];
                        for (int read; (read = reader.read(buffer)) != -1;) for (int i = 0; i < read; i++) metrics.accept(buffer[i]);
                    }
                    metrics.finish();
                    int coder = metrics.nonLatin1 == 0 ? 0 : 1;
                    String[] counts = new String[COMMANDS.length];
                    for (int i = 0; i < counts.length; i++) counts[i] = COMMANDS[i] + ":" + metrics.commands[i];
                    output.write(parts[0] + "\t" + parts[1] + "\t" + parts[3] + "\t" + entry.getSize() + "\t" + metrics.units + "\t" + metrics.utf8Bytes + "\t" + coder + "\t" + metrics.units * (coder + 1L) + "\t" + metrics.nonLatin1 + "\t" + metrics.supplementary + "\t" + metrics.replacements + "\t" + metrics.lines + "\t" + HexFormat.of().formatHex(hash.digest()) + "\t" + String.join(";", counts) + "\n");
                }
                if (++count % 200 == 0) { output.flush(); System.out.println("Measured " + count + " pinned text entries"); }
            }
            System.out.println("Completed " + count + " pinned text entries");
        }
    }
}
