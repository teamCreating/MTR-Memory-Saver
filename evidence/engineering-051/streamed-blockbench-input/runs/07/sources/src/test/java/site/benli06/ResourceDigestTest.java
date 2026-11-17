package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Random;
import org.junit.jupiter.api.Test;

class ResourceDigestTest {
    @Test void streamedDigestMatchesIndependentUtf8IncludingMalformedBoundaries() throws Exception {
        Random random = new Random(42);
        for (int size : new int[] {0, 1, 4095, 4096, 4097, 8193, 65536}) {
            char[] units = new char[size];
            for (int i = 0; i < size; i++) units[i] = (char) random.nextInt(65536);
            String raw = new String(units);
            assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8))),
                    ResourceTextDigest.sha256(raw));
        }
        String boundary = "a".repeat(4095) + "\ud800\udc00" + "\ud800";
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(boundary.getBytes(StandardCharsets.UTF_8))), ResourceTextDigest.sha256(boundary));
    }
}
