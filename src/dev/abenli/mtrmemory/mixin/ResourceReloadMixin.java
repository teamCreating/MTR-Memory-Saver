package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SharedBlockbenchCache;

import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class ResourceReloadMixin {
    @Inject(method = "reload", at = @At("HEAD"))
    private static void startEpoch(CallbackInfo callback) {
        SharedBlockbenchCache.beginReload();
    }

    @Inject(method = "reload", at = @At("RETURN"))
    private static void logSharing(CallbackInfo callback) {
        SharedBlockbenchCache.report();
    }
}
