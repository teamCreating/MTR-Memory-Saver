package site.benli06.mixin;

import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;
import site.benli06.StrictResourceText;

/** Preserve native missing-resource semantics while propagating failures of existing resources. */
@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class ResourceTextReadMixin {
    @Redirect(method = "lambda$readResource$22(Lnet/minecraft/resources/ResourceLocation;Ljava/lang/String;)Ljava/lang/String;",
            at = @At(value = "INVOKE", target = "Lorg/mtr/resource/ResourceManagerHelper;readResource(Lnet/minecraft/resources/ResourceLocation;)Ljava/lang/String;"))
    private static String read(ResourceLocation resourceId) {
        var resource = Minecraft.getInstance().getResourceManager().getResource(resourceId);
        if (resource.isEmpty()) return "";
        return StrictResourceText.read(resourceId.toString(), resource.get()::open);
    }
}
