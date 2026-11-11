package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SharedBlockbenchCache;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class SourceLifetimeMixin {
    @Inject(method = "reload", at = @At("RETURN"))
    private static void releaseSources(CallbackInfo callback) {
        SharedBlockbenchCache.finishRegistration();
    }
}
