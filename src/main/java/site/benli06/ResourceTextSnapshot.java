package site.benli06;

import java.io.IOException;
import java.io.FilterReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import org.apache.commons.io.input.ReaderInputStream;

/** Immutable decoded input and its old String.getBytes(UTF_8) content identity. */
public final class ResourceTextSnapshot implements AutoCloseable {
    private final Utf16TextSnapshot snapshot;
    private final ReadAdmission admission;
    private final long length;
    private final String digest;

    private ResourceTextSnapshot(Utf16TextSnapshot snapshot, ReadAdmission admission, long length, String digest) {
        this.snapshot = snapshot; this.admission = admission; this.length = length; this.digest = digest;
    }

    /** The caller retains ownership of input; the returned snapshot owns its channel. */
    public static ResourceTextSnapshot capture(InputStream input, Charset charset, ReadAdmission admission) throws IOException {
        return capture(input, charset, admission, null);
    }

    /** Close the source before transferring snapshot ownership, including a source-close failure. */
    public static ResourceTextSnapshot open(StrictResourceText.StreamOpener source, Charset charset, ReadAdmission admission) throws IOException {
        return open(source, charset, admission, null);
    }

    static ResourceTextSnapshot open(StrictResourceText.StreamOpener source, Charset charset, ReadAdmission admission, Path directory) throws IOException {
        ResourceTextSnapshot result = null;
        try (var scope = admission.open()) {
            try (InputStream input = source.open()) { result = capture(input, charset, admission, directory); }
            return result;
        } catch (Throwable error) {
            if (result != null) {
                try { result.close(); }
                catch (Throwable cleanup) { if (cleanup != error) error.addSuppressed(cleanup); }
            }
            throw error;
        }
    }

    static ResourceTextSnapshot capture(InputStream input, Charset charset, ReadAdmission admission, Path directory) throws IOException {
        Utf16TextSnapshot snapshot = new Utf16TextSnapshot(directory);
        try (var scope = admission.open()) {
            snapshot.begin(List.of(), admission);
            var decoded = new InputStreamReader(input, charset == null ? Charset.defaultCharset() : charset);
            // The digest consumes the decoded stream while the same characters are
            // captured. The caller continues to own the source stream.
            var captured = new FilterReader(decoded) {
                private long length;
                @Override public int read(char[] chars, int offset, int count) throws IOException {
                    int read = super.read(chars, offset, count);
                    if (read > 0) {
                        length += read;
                        admission.checkLength(length);
                        snapshot.write(chars, offset, read, admission);
                    }
                    return read;
                }
            };
            String digest = ResourceTextDigest.sha256(captured);
            admission.checkLength(captured.length);
            return new ResourceTextSnapshot(snapshot, admission, captured.length, digest);
        } catch (Throwable error) {
            try { snapshot.close(); }
            catch (Throwable cleanup) { if (cleanup != error) error.addSuppressed(cleanup); }
            throw error;
        }
    }

    public long length() { return length; }
    public String digest() { return digest; }
    public Reader reader() throws IOException { return snapshot.reader(length, admission); }
    /** Preserves String.getBytes(UTF_8), including replacement, with bounded buffers. */
    public InputStream utf8Stream() throws IOException { return utf8Stream(reader()); }
    static InputStream utf8Stream(Reader reader) {
        return new ReaderInputStream(reader, StandardCharsets.UTF_8, 8192);
    }
    @Override public void close() throws IOException { snapshot.close(); }
}
