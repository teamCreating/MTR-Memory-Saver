package site.benli06;

import java.io.InputStream;
import java.util.List;
import java.util.Set;
import net.neoforged.fml.loading.LoadingModList;
import org.mtr.libraries.com.google.gson.JsonParser;
import org.objectweb.asm.tree.ClassNode;
import org.spongepowered.asm.launch.MixinInitialisationError;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

/** Refuse a same-version replacement binary before installing version-sensitive Mixins. */
public final class CompatibilityPlugin implements IMixinConfigPlugin {
    @Override public void onLoad(String mixinPackage) {
        try (InputStream input = getClass().getResourceAsStream("/mtr-memory-target.json")) {
            if (input == null) throw new IllegalStateException("Missing build target metadata");
            var target = JsonParser.parseString(new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
            var list = LoadingModList.get();
            var file = list == null ? null : list.getModFileById("mtr");
            if (file == null) throw new IllegalStateException("MTR is not available during compatibility verification");
            BinaryFingerprint.require(file.getFile().getFilePath(), target.get("mtrSha256").getAsString());
        } catch (Exception error) {
            // Mixin treats Exceptions during configuration selection as optional failures.
            // Its standard fatal initialization type preserves this required prerequisite.
            throw new MixinInitialisationError("MTR Memory Saver cannot apply this build to the loaded MTR binary", error);
        }
    }

    @Override public String getRefMapperConfig() { return null; }
    @Override public boolean shouldApplyMixin(String target, String mixin) { return true; }
    @Override public void acceptTargets(Set<String> mine, Set<String> others) {}
    @Override public List<String> getMixins() { return null; }
    @Override public void preApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
    @Override public void postApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
}
