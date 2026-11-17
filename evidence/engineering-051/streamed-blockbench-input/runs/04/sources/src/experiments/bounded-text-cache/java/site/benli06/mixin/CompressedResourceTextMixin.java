package site.benli06.mixin;

import site.benli06.CompressedResourceTextCache;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import org.mtr.MTR;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.Redirect;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class CompressedResourceTextMixin {
    @Redirect(method = "readResource(Lnet/minecraft/resources/ResourceLocation;)Ljava/lang/String;",
            at = @At(value = "INVOKE", target = "Ljava/util/concurrent/ConcurrentMap;computeIfAbsent(Ljava/lang/Object;Ljava/util/function/Function;)Ljava/lang/Object;"))
    private static Object read(ConcurrentMap<String, String> nativeCache, Object key, Function<String, String> reader) {
        return CompressedResourceTextCache.get((String) key, reader);
    }

    @Inject(method = "reload", at = @At("HEAD"))
    private static void begin(CallbackInfo callback) { CompressedResourceTextCache.clear(); }

    @Inject(method = "reload", at = @At("RETURN"))
    private static void finish(CallbackInfo callback) {
        long[] stats = CompressedResourceTextCache.statistics();
        long[] budget = CompressedResourceTextCache.budgetStatistics();
        CompressedResourceTextCache.clear();
        MTR.LOGGER.info("MTR compressed text: {} entries, {} compressed, {} input code units, {} packed bytes, {} uncompressed code units; cache released",
                stats[0], stats[1], stats[2], stats[3], stats[4]);
        MTR.LOGGER.info("MTR resource text budget: {} bytes, {} retained weight, {} peak admitted weight, {} evictions",
                budget[0], budget[1], budget[2], budget[3]);
    }
}
