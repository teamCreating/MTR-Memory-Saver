package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SharedBlockbenchCache;

import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = VehicleModel.class, remap = false)
abstract class VehicleModelFactoryMixin {
    @Inject(method = "getModelLoaderBase", at = @At("HEAD"), cancellable = true)
    private static void share(String model, String texture, ResourceProvider provider, boolean flipV,
                              CallbackInfoReturnable<ModelLoaderBase> callback) {
        if (model.endsWith(".bbmodel")) {
            callback.setReturnValue(SharedBlockbenchCache.get(model, texture, provider, flipV));
        }
    }
}
