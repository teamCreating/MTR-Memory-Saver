package site.benli06.probe.mixin;

import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import site.benli06.probe.PackagedClientObservation;

/** Records actual method boundaries without changing registration, parsing or cache state. */
@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class ResourceEpochObservationMixin {
    @Inject(method = "reload", at = @At("HEAD"))
    private static void started(CallbackInfo callback) {
        PackagedClientObservation.reloadStarted();
    }

    @Inject(method = "reload", at = @At("RETURN"))
    private static void returned(CallbackInfo callback) {
        PackagedClientObservation.reloadReturned();
    }
}
