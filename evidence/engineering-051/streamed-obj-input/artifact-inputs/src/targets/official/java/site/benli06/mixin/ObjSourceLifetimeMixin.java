package site.benli06.mixin;

import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import site.benli06.StreamedObjCache;

@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class ObjSourceLifetimeMixin {
    @Inject(method = "reload", at = @At("HEAD"))
    private static void begin(CallbackInfo callback) { StreamedObjCache.beginReload(); }
    @Inject(method = "reload", at = @At("RETURN"))
    private static void finish(CallbackInfo callback) {
        StreamedObjCache.report();
        StreamedObjCache.finishRegistration();
    }
}
