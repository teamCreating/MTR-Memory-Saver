package site.benli06;

import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** Hashes the same UTF-8 bytes as String.getBytes without a large temporary copy. */
public final class ResourceTextDigest {
    private static final int SMALL_TEXT_UNITS = 4096;
    private static final int BUFFER_BYTES = 8192;

    private ResourceTextDigest() {}

    public static String sha256(String raw) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            if (raw.length() <= SMALL_TEXT_UNITS) {
                return HexFormat.of().formatHex(digest.digest(raw.getBytes(StandardCharsets.UTF_8)));
            }
            // String.getBytes replaces malformed UTF-16 with the charset's
            // default replacement. Reuse bounded array-backed buffers so the
            // encoder can use its array path. compact() carries an unfinished
            // high surrogate into the next input segment.
            var encoder = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPLACE)
                    .onUnmappableCharacter(CodingErrorAction.REPLACE);
            CharBuffer input = CharBuffer.allocate(SMALL_TEXT_UNITS);
            input.limit(0);
            ByteBuffer output = ByteBuffer.allocate(BUFFER_BYTES);
            CoderResult result;
            int offset = 0;
            while (true) {
                if (Thread.currentThread().isInterrupted()) throw new java.util.concurrent.CancellationException("Resource digest interrupted");
                input.compact();
                int count = Math.min(input.remaining(), raw.length() - offset);
                raw.getChars(offset, offset + count, input.array(), input.position());
                input.position(input.position() + count);
                offset += count;
                input.flip();
                boolean finished = offset == raw.length();
                do {
                    result = encoder.encode(input, output, finished);
                    update(digest, output, result);
                } while (result.isOverflow());
                if (finished) break;
            }
            do {
                result = encoder.flush(output);
                update(digest, output, result);
            } while (result.isOverflow());
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private static void update(MessageDigest digest, ByteBuffer output, CoderResult result) {
        if (result.isError()) throw new IllegalStateException("UTF-8 encoding failed: " + result);
        digest.update(output.array(), 0, output.position());
        output.clear();
    }
}
