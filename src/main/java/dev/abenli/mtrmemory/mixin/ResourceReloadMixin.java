package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SharedBlockbenchCache;
import java.util.concurrent.ConcurrentMap;
import org.mtr.MTR;

import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class ResourceReloadMixin {
    @Shadow @Final private static ConcurrentMap<String, String> RESOURCE_CACHE;
    @Inject(method = "reload", at = @At("HEAD"))
    private static void startEpoch(CallbackInfo callback) {
        SharedBlockbenchCache.beginReload();
    }

    @Inject(method = "reload", at = @At("RETURN"))
    private static void logSharing(CallbackInfo callback) {
        SharedBlockbenchCache.report();
        // Parsers own their input strings; later reads repopulate this read-through cache.
        int entries = RESOURCE_CACHE.size();
        RESOURCE_CACHE.clear();
        MTR.LOGGER.info("MTR memory sharing: released {} cached source-text entries after registration", entries);
    }
}
