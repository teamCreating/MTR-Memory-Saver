package dev.abenli.neutralprobe.mixin;

import dev.abenli.neutralprobe.NativeObserver;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = CustomResourceLoader.class, remap = false)
public abstract class NativeResourceEpochMixin {
    @Inject(method = "reload()V", at = @At("HEAD"))
    private static void neutralHead(CallbackInfo ignored) { NativeObserver.reloadStarted(); }
    @Inject(method = "reload()V", at = @At("RETURN"))
    private static void neutralReturn(CallbackInfo ignored) { NativeObserver.reloadReturned(); }
}
