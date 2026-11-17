package dev.abenli.neutralprobe;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.mtr.libraries.com.google.gson.JsonObject;

public record NativeTarget(String target, String minecraft, int java, String neoForge, String mtrSha256) {
    public static NativeTarget from(JsonObject value) {
        if (value.get("schema_version").getAsInt() != 1 || !"official".equals(value.get("variant").getAsString())
                || !"official-native-observer".equals(value.get("probe_kind").getAsString()))
            throw new IllegalArgumentException("Unsupported native observer metadata");
        return new NativeTarget(value.get("target").getAsString(), value.get("minecraft").getAsString(),
                value.get("java").getAsInt(), value.get("neoForge").getAsString(), value.get("mtrSha256").getAsString());
    }
    public void requireRuntime(String actualMinecraft, int actualJava, String actualNeoForge, Path mtrJar) throws IOException {
        if (!minecraft.equals(actualMinecraft) || java != actualJava || !neoForge.equals(actualNeoForge))
            throw new IllegalStateException("Native observer runtime differs from its exact build target " + target);
        if (!mtrSha256.equals(sha256(mtrJar)))
            throw new IllegalStateException("Native observer MTR fingerprint differs from its audited official binary");
    }
    public static String sha256(Path path) throws IOException {
        final MessageDigest digest;
        try { digest = MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[65536];
            for (int count; (count = input.read(buffer)) != -1;) digest.update(buffer, 0, count);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
