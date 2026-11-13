package site.benli06;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class CompatibilityPluginTest {
    @TempDir Path directory;

    @Test void acceptsTheExactBytes() throws Exception {
        byte[] data = {0, 3, 1, 4, 9};
        Path path = Files.write(directory.resolve("release.jar"), data);
        String expected = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
        assertDoesNotThrow(() -> BinaryFingerprint.require(path, expected));
    }

    @Test void rejectsSameNameDifferentBytes() throws Exception {
        byte[] original = "same version first binary".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String expected = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(original));
        Path path = Files.write(directory.resolve("release.jar"), "same version patched binary".getBytes());
        assertThrows(IllegalStateException.class, () -> BinaryFingerprint.require(path, expected));
    }

    @Test void missingDependencyCannotPass() {
        assertThrows(java.io.IOException.class, () ->
                BinaryFingerprint.require(directory.resolve("missing.jar"), "0".repeat(64)));
    }
}
