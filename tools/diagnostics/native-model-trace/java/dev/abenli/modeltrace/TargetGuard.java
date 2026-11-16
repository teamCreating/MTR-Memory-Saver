package dev.abenli.modeltrace;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.fml.loading.LoadingModList;
import org.mtr.libraries.com.google.gson.JsonObject;
import org.mtr.libraries.com.google.gson.JsonParser;
import org.objectweb.asm.tree.ClassNode;
import org.spongepowered.asm.launch.MixinInitialisationError;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

public final class TargetGuard implements IMixinConfigPlugin {
    public static JsonObject metadata() throws IOException {
        try (var input = TargetGuard.class.getResourceAsStream("/mtr-model-trace-target.json")) {
            if (input == null) throw new IOException("Missing model trace target");
            return JsonParser.parseString(new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
        }
    }
    static String sha256(Path file) throws Exception {
        var digest = MessageDigest.getInstance("SHA-256");
        try (var input = Files.newInputStream(file)) {
            byte[] buffer = new byte[65536]; for (int count; (count = input.read(buffer)) != -1;) digest.update(buffer, 0, count);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
    static void verify(JsonObject target, String minecraft, int java, String neoForge, String hash) {
        if (target.get("schema_version").getAsInt() != 1 || !"official".equals(target.get("variant").getAsString())
                || !target.get("minecraft").getAsString().equals(minecraft) || target.get("java").getAsInt() != java
                || !target.get("neoForge").getAsString().equals(neoForge) || !target.get("mtrSha256").getAsString().equals(hash))
            throw new IllegalStateException("Native model trace target or MTR fingerprint differs from the exact audited target");
    }
    @Override public void onLoad(String mixinPackage) {
        try {
            var files = LoadingModList.get(); var mtr = files == null ? null : files.getModFileById("mtr");
            if (mtr == null) throw new IllegalStateException("MTR is unavailable for diagnostic verification");
            verify(metadata(), FMLLoader.versionInfo().mcVersion(), Runtime.version().feature(),
                    FMLLoader.versionInfo().neoForgeVersion(), sha256(mtr.getFile().getFilePath()));
        } catch (Exception failure) {
            throw new MixinInitialisationError("The native model diagnostic cannot apply to this client", failure);
        }
    }
    @Override public String getRefMapperConfig() { return null; }
    @Override public boolean shouldApplyMixin(String target, String mixin) { return true; }
    @Override public void acceptTargets(Set<String> mine, Set<String> others) {}
    @Override public List<String> getMixins() { return null; }
    @Override public void preApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
    @Override public void postApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
}
