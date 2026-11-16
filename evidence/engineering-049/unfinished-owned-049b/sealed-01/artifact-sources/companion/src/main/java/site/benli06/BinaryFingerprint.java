package site.benli06;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

/** Dependency identity verification independent of Minecraft and the Mixin runtime. */
public final class BinaryFingerprint {
    private BinaryFingerprint() {}

    public static void require(Path jar, String expected) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(jar)) {
            byte[] bytes = new byte[65536];
            for (int count; (count = input.read(bytes)) != -1;) digest.update(bytes, 0, count);
        }
        if (!HexFormat.of().formatHex(digest.digest()).equals(expected)) {
            throw new IllegalStateException("Loaded MTR fingerprint does not match the audited build target");
        }
    }
}
