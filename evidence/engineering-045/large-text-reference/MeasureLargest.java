import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;
import org.apache.commons.io.IOUtils;

/** Actual native IOUtils String construction and compact-coder observation. */
public final class MeasureLargest {
    public static void main(String[] args) throws Exception {
        var fields = Files.readString(Path.of(args[0]), StandardCharsets.UTF_8).strip().split("\t", -1);
        try (var zip = new ZipFile(fields[2]); var stream = zip.getInputStream(zip.getEntry(fields[3]))) {
            String raw = IOUtils.toString(stream, StandardCharsets.UTF_8);
            var coderField = String.class.getDeclaredField("coder"); coderField.setAccessible(true);
            var valueField = String.class.getDeclaredField("value"); valueField.setAccessible(true);
            byte coder = coderField.getByte(raw);
            byte[] backing = (byte[]) valueField.get(raw);
            byte[] encoded = raw.getBytes(StandardCharsets.UTF_8);
            String report = "{\"decoded_utf16_units\":" + raw.length() + ",\"actual_string_coder\":" + coder + ",\"actual_string_backing_bytes\":" + backing.length + ",\"native_reencoded_utf8_bytes\":" + encoded.length + ",\"native_reencoded_sha256\":\"" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(encoded)) + "\",\"max_heap_bytes\":" + Runtime.getRuntime().maxMemory() + "}";
            Files.writeString(Path.of(args[1]), report + "\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
            System.out.println(report);
        }
    }
}
