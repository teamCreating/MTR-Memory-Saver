package site.benli06;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

/** Reads an existing resource without converting an I/O or size failure into empty text. */
public final class StrictResourceText {
    @FunctionalInterface
    public interface StreamOpener { InputStream open() throws IOException; }

    private StrictResourceText() {}

    public static String read(String resource, StreamOpener source) {
        return read(resource, source, ReadAdmission.GLOBAL);
    }

    static String read(String resource, StreamOpener source, ReadAdmission admission) {
        // Admit before opening; the scope also covers stream close and nested segmented decoding.
        try (var scope = admission.open(); InputStream input = source.open()) {
            return SegmentedResourceText.read(input, StandardCharsets.UTF_8, admission);
        } catch (IOException error) {
            throw new UncheckedIOException(resource, error);
        }
    }
}
