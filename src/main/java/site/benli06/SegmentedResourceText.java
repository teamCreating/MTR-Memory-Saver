package site.benli06;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Decodes native resource text without repeatedly growing its complete backing array. */
public final class SegmentedResourceText {
    private SegmentedResourceText() {}

    public static String read(InputStream input, Charset charset) throws IOException {
        return read(input, charset, ReadAdmission.GLOBAL);
    }

    public static String read(InputStream input, Charset charset, ReadAdmission admission) throws IOException {
        return read(input, charset, admission, null);
    }

    static String read(InputStream input, Charset charset, ReadAdmission admission, Path temporaryDirectory) throws IOException {
        try (var scope = admission.open()) {
            // The native resource helper owns and closes the original stream.
            InputStreamReader reader = new InputStreamReader(input, charset == null ? Charset.defaultCharset() : charset);
            char[] buffer = new char[8192];
            List<String> segments = new ArrayList<>();
            long length = 0;
            TextWorkspace workspace = admission.workspace();
            try (Utf16TextSnapshot snapshot = new Utf16TextSnapshot(temporaryDirectory);
                 var share = workspace.claim(workspace.share())) {
                for (int count; (count = reader.read(buffer)) != -1;) {
                    length += count;
                    admission.checkLength(length);
                    if (count == 0) continue;
                    if (!snapshot.exists() && 4L * length > workspace.share()) {
                        snapshot.begin(segments, admission);
                        segments.clear();
                        // No payload reservation is held while awaiting a larger atomic claim.
                        share.close();
                    }
                    if (snapshot.exists()) snapshot.write(buffer, count, admission);
                    else segments.add(new String(buffer, 0, count));
                }
                admission.checkLength(length);
                if (!snapshot.exists()) return String.join("", segments);
                snapshot.rewind();
                try (var full = workspace.claim(4L * length)) {
                    return snapshot.restore(length, admission);
                }
            }
        }
    }

}
