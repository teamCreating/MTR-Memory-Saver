package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.VehicleJsonCache;
import org.mtr.resource.VehicleModel;
import org.mtr.libraries.com.google.gson.JsonObject;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(value = VehicleModel.class, remap = false)
abstract class VehicleJsonCacheMixin {
    @Redirect(method = "<init>", at = @At(value = "INVOKE", target = "Lorg/mtr/core/tool/Utilities;parseJson(Ljava/lang/String;)Lorg/mtr/libraries/com/google/gson/JsonObject;"))
    private JsonObject shareConfiguration(String raw) {
        return VehicleJsonCache.parse(raw);
    }
}
