package site.benli06.mixin;

import org.mtr.Keys;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import site.benli06.SnapshotResourceProvider;
import site.benli06.StreamedObjCache;

@Mixin(value = VehicleModel.class, remap = false)
abstract class ObjVehicleFactoryMixin {
    @Inject(method = "getModelLoaderBase", at = @At("HEAD"), cancellable = true)
    private static void streamObj(String model, String texture, ResourceProvider provider, boolean flipV,
                                  CallbackInfoReturnable<ModelLoaderBase> callback) {
        if (model.endsWith(".obj") && provider instanceof SnapshotResourceProvider snapshots && !Keys.DEBUG)
            callback.setReturnValue(StreamedObjCache.get(model, texture, snapshots, flipV));
    }
}
