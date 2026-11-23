package dev.abenli.neutralprobe.mixin;

import dev.abenli.neutralprobe.NativeModelDiagnostics;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = VehicleModel.class, remap = false)
public abstract class NativeInvalidModelMixin {
    @Inject(method = "getModelLoaderBase(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;",
            at = @At(value = "INVOKE", target = "Lorg/apache/logging/log4j/Logger;error(Ljava/lang/String;Ljava/lang/Object;)V"), require = 1, allow = 1)
    private static void nativeInvalidLog(String model, String texture, ResourceProvider provider, boolean flip,
            CallbackInfoReturnable<ModelLoaderBase> ignored) {
        NativeModelDiagnostics.beforeLog(model, texture, flip);
    }
    @Inject(method = "getModelLoaderBase(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;",
            at = @At("TAIL"), require = 1, allow = 1)
    private static void nativeFallbackReturn(String model, String texture, ResourceProvider provider, boolean flip,
            CallbackInfoReturnable<ModelLoaderBase> result) {
        if (NativeModelDiagnostics.unsupported(model)) NativeModelDiagnostics.returned(model, texture, flip,
                result.getReturnValue() == null ? null : result.getReturnValue().getClass().getName());
    }
}
