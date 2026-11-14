package dev.abenli.neutralprobe;

import java.util.List;
import java.util.Set;
import net.neoforged.fml.loading.FMLLoader;
import net.neoforged.fml.loading.LoadingModList;
import org.objectweb.asm.tree.ClassNode;
import org.spongepowered.asm.launch.MixinInitialisationError;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

/** Guards the native ABI; this class has no companion linkage or reflection. */
public final class NativeCompatibilityPlugin implements IMixinConfigPlugin {
    @Override public void onLoad(String mixinPackage) {
        try {
            var target = NativeTarget.from(ObservationSchema.resource("/mtr-native-observer-target.json"));
            var list = LoadingModList.get();
            var mtrFile = list == null ? null : list.getModFileById("mtr");
            if (mtrFile == null) throw new IllegalStateException("MTR is unavailable for native observer verification");
            target.requireRuntime(FMLLoader.versionInfo().mcVersion(), Runtime.version().feature(),
                    FMLLoader.versionInfo().neoForgeVersion(), mtrFile.getFile().getFilePath());
            if (list.getModFileById("vehicle_performance_probe") != null)
                throw new IllegalStateException("Multiple client frame observation providers are installed");
        } catch (Exception failure) {
            throw new MixinInitialisationError("The native observer cannot apply to this client", failure);
        }
    }
    @Override public String getRefMapperConfig() { return null; }
    @Override public boolean shouldApplyMixin(String target, String mixin) { return true; }
    @Override public void acceptTargets(Set<String> mine, Set<String> others) {}
    @Override public List<String> getMixins() { return null; }
    @Override public void preApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
    @Override public void postApply(String target, ClassNode node, String mixin, IMixinInfo info) {}
}
