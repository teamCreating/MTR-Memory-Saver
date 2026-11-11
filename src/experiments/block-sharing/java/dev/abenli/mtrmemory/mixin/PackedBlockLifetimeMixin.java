package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.PackedVertices;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Cache-owned keys live only during native resource registration. */
@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class PackedBlockLifetimeMixin {
    @Inject(method = "reload", at = @At("HEAD"))
    private static void begin(CallbackInfo callback) { PackedVertices.beginSharing(); }

    @Inject(method = "reload", at = @At("RETURN"))
    private static void release(CallbackInfo callback) { PackedVertices.finishSharing(); }
}
