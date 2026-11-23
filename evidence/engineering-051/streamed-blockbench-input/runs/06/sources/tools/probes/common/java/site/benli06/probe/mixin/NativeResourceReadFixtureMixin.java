package site.benli06.probe.mixin;

import java.util.Optional;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.resources.MultiPackResourceManager;
import net.minecraft.server.packs.resources.Resource;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import site.benli06.probe.NativeResourceReadFixture;

/** Supplies actual native Resource streams only for active acceptance fixture identities. */
@Mixin(value = MultiPackResourceManager.class, remap = false)
abstract class NativeResourceReadFixtureMixin {
    @Inject(method = "getResource(Lnet/minecraft/resources/ResourceLocation;)Ljava/util/Optional;", at = @At("HEAD"), cancellable = true)
    private void fixture(ResourceLocation id, CallbackInfoReturnable<Optional<Resource>> callback) {
        var lookup = NativeResourceReadFixture.lookup(id);
        if (lookup.intercepted()) callback.setReturnValue(lookup.resource());
    }
}
