package site.benli06.mixin;

import site.benli06.SharedBlockbenchCache;

import org.mtr.model.ModelLoaderBase;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = ModelLoaderBase.class, remap = false)
abstract class ModelLoaderCompletionMixin {
    @Inject(method = "setModelLoaded", at = @At("RETURN"))
    private void publish(CallbackInfo callback) {
        SharedBlockbenchCache.completed((ModelLoaderBase) (Object) this);
    }
}
