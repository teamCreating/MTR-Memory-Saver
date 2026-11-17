package site.benli06.probe.mixin;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import site.benli06.SharedBlockbenchCache;
import site.benli06.probe.NativeParserPause;

/** Pause after the real native parseStarted ticket, before the original parser Runnable executes. */
@Mixin(value = SharedBlockbenchCache.class, remap = false)
abstract class NativeParserPauseMixin {
    @Inject(method = "submitNative", at = @At("HEAD"))
    private static void pause(ExecutorService executor, Runnable parse, CallbackInfoReturnable<Future<?>> callback) {
        NativeParserPause.beforeSubmit();
    }
}
