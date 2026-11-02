package dev.abenli.mtrmemory.mixin;

import java.util.function.Supplier;
import dev.abenli.mtrmemory.SharedBlockbenchCache;
import org.mtr.model.BlockbenchModelLoader;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.BlockbenchModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = BlockbenchModelLoader.class, remap = false)
abstract class SourceParseCompletionMixin {
    @Inject(method = "lambda$loadModel$5(Ljava/util/function/Supplier;)V", at = @At(value = "INVOKE", target = "Lorg/mtr/model/BlockbenchModelLoader;parseFinished()V"))
    private void cleanupAttempt(Supplier<BlockbenchModel> model, CallbackInfo callback) {
        SharedBlockbenchCache.finishParseAttempt((ModelLoaderBase) (Object) this);
    }
}
