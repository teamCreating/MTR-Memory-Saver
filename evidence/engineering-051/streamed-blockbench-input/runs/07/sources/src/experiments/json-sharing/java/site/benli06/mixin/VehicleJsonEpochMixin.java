package site.benli06.mixin;

import site.benli06.VehicleJsonCache;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class VehicleJsonEpochMixin {
    @Inject(method = "reload", at = @At("HEAD"))
    private static void startJsonEpoch(CallbackInfo callback) {
        VehicleJsonCache.beginReload();
    }

    @Inject(method = "reload", at = @At("RETURN"))
    private static void releaseJsonReferences(CallbackInfo callback) {
        VehicleJsonCache.finishRegistration();
    }
}
