package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SharedBlockbenchCache;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(value = VehicleModel.class, remap = false)
abstract class VehicleSourceSelectionMixin {
    @Redirect(method = "<init>", at = @At(value = "INVOKE", target = "Lorg/mtr/resource/VehicleModel;getModelLoaderBase(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;"))
    private static ModelLoaderBase selected(String model, String texture, ResourceProvider provider, boolean flipV) {
        return model.endsWith(".bbmodel") ? SharedBlockbenchCache.getForVehicle(model, texture, provider, flipV)
                : VehicleModel.getModelLoaderBase(model, texture, provider, flipV);
    }
}
