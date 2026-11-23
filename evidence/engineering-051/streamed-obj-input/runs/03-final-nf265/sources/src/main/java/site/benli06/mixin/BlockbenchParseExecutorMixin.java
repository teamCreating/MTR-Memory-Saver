package site.benli06.mixin;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import org.mtr.model.BlockbenchModelLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;
import site.benli06.SharedBlockbenchCache;

@Mixin(value = BlockbenchModelLoader.class, remap = false)
abstract class BlockbenchParseExecutorMixin {
    @Redirect(method = "loadModel(Ljava/util/function/Supplier;)V", at = @At(value = "INVOKE",
            target = "Ljava/util/concurrent/ExecutorService;submit(Ljava/lang/Runnable;)Ljava/util/concurrent/Future;"))
    private Future<?> admittedParse(ExecutorService executor, Runnable parse) {
        return SharedBlockbenchCache.submitNative(executor, parse);
    }
}
