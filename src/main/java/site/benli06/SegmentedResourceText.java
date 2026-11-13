package site.benli06;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.List;

/** Decodes native resource text without repeatedly growing its complete backing array. */
public final class SegmentedResourceText {
    private SegmentedResourceText() {}

    public static String read(InputStream input, Charset charset) throws IOException {
        return read(input, charset, ReadAdmission.GLOBAL);
    }

    public static String read(InputStream input, Charset charset, ReadAdmission admission) throws IOException {
        try (var scope = admission.open()) {
        // The native resource helper owns and closes the original stream.
        InputStreamReader reader = new InputStreamReader(input, charset == null ? Charset.defaultCharset() : charset);
        char[] buffer = new char[8192];
        List<String> segments = new ArrayList<>();
        long length = 0;
        for (int count; (count = reader.read(buffer)) != -1;) {
            length += count;
            admission.checkLength(length);
            if (count != 0) segments.add(new String(buffer, 0, count));
        }
        // String.join allocates the final payload once and preserves UTF-16 units
        // even if a supplementary character crosses a segment boundary.
        return String.join("", segments);
        }
    }
}
