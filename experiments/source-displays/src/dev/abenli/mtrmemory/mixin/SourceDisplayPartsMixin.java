package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SharedBlockbenchCache;
import org.mtr.model.ModelLoaderBase;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = ModelLoaderBase.class, remap = false)
abstract class SourceDisplayPartsMixin {
    @Inject(method = "addModelDisplayParts", at = @At("HEAD"), cancellable = true)
    private void retainSelected(String name, ObjectArrayList<?> parts, CallbackInfo callback) {
        if (!SharedBlockbenchCache.retainDisplay((ModelLoaderBase) (Object) this, name, parts.size())) callback.cancel();
    }
}
