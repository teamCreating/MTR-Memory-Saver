package site.benli06.mixin;

import site.benli06.SharedBlockbenchLoader;
import org.mtr.model.ModelLoaderBase;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Keep v6's native disposal; prevent a late shared result from repopulating a closed facade. */
@Mixin(value = ModelLoaderBase.class, remap = false)
abstract class V6LoaderLifecycleMixin {
    @Inject(method = "close", at = @At("HEAD"))
    private void closeSharedConsumer(CallbackInfo callback) {
        if ((Object) this instanceof SharedBlockbenchLoader shared) shared.beforeNativeClose();
    }
}
