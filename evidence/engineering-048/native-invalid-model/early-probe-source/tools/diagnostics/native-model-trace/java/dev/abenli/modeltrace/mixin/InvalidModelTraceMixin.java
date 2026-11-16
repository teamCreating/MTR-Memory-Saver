package dev.abenli.modeltrace.mixin;

import dev.abenli.modeltrace.TraceRecorder;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ResourceProvider;
import org.mtr.resource.VehicleModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = VehicleModel.class, remap = false)
public abstract class InvalidModelTraceMixin {
    @Inject(method = "getModelLoaderBase(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;",
            at = @At(value = "INVOKE", target = "Lorg/apache/logging/log4j/Logger;error(Ljava/lang/String;Ljava/lang/Object;)V"), require = 1, allow = 1)
    private static void modelTraceInvalid(String model, String texture, ResourceProvider provider, boolean flip,
            CallbackInfoReturnable<ModelLoaderBase> ignored) {
        TraceRecorder.record("before_native_invalid_log", model, texture, flip, null);
    }
    @Inject(method = "getModelLoaderBase(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;",
            at = @At("RETURN"), require = 1, allow = 1)
    private static void modelTraceReturn(String model, String texture, ResourceProvider provider, boolean flip,
            CallbackInfoReturnable<ModelLoaderBase> result) {
        if (TraceRecorder.unsupported(model)) TraceRecorder.record("native_fallback_return", model, texture, flip,
                result.getReturnValue() == null ? null : result.getReturnValue().getClass().getName());
    }
}
