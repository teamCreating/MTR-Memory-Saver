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
            // default replacement. The encoder consumes the original String
            // directly, including surrogate pairs at output-buffer boundaries.
            var encoder = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPLACE)
                    .onUnmappableCharacter(CodingErrorAction.REPLACE);
            CharBuffer input = CharBuffer.wrap(raw);
            ByteBuffer output = ByteBuffer.allocate(BUFFER_BYTES);
            CoderResult result;
            do {
                result = encoder.encode(input, output, true);
                update(digest, output, result);
            } while (result.isOverflow());
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
