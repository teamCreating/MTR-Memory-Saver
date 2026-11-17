package site.benli06.mixin;

import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import org.mtr.client.CustomResourceLoader;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import org.mtr.resource.ResourceProvider;
import site.benli06.NativeResourceSnapshots;
import site.benli06.StrictResourceText;

/** Preserve native missing-resource semantics while propagating failures of existing resources. */
@Mixin(value = CustomResourceLoader.class, remap = false)
abstract class ResourceTextReadMixin {
    @ModifyArg(method = "reload", index = 2, at = @At(value = "INVOKE",
            target = "Lorg/mtr/resource/RailResource;<init>(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;)V"))
    private static ResourceProvider nativeRailProvider(ResourceProvider original) {
        return NativeResourceSnapshots.wrap(original);
    }

    @ModifyArg(method = "reload", index = 1, at = @At(value = "INVOKE",
            target = "Lorg/mtr/legacy/resource/CustomResourcesConverter;convertRails(Ljava/util/function/Consumer;Lorg/mtr/resource/ResourceProvider;)V"))
    private static ResourceProvider nativeLegacyRailProvider(ResourceProvider original) {
        return NativeResourceSnapshots.wrap(original);
    }

    @ModifyArg(method = "reload", index = 1, at = @At(value = "INVOKE",
            target = "Lorg/mtr/legacy/resource/CustomResourcesConverter;convertObjects(Ljava/util/function/Consumer;Lorg/mtr/resource/ResourceProvider;)V"))
    private static ResourceProvider nativeLegacyObjectProvider(ResourceProvider original) {
        return NativeResourceSnapshots.wrap(original);
    }

    @ModifyArg(method = {"lambda$reload$8", "lambda$reload$10"}, index = 1, require = 2, at = @At(value = "INVOKE",
            target = "Lorg/mtr/legacy/resource/CustomResourcesConverter;convert(Lorg/mtr/libraries/com/google/gson/JsonObject;Lorg/mtr/resource/ResourceProvider;)Lorg/mtr/resource/CustomResources;"))
    private static ResourceProvider nativeConvertedProvider(ResourceProvider original) {
        return NativeResourceSnapshots.wrap(original);
    }

    @Redirect(method = "lambda$readResource$22(Lnet/minecraft/resources/ResourceLocation;Ljava/lang/String;)Ljava/lang/String;",
            at = @At(value = "INVOKE", target = "Lorg/mtr/resource/ResourceManagerHelper;readResource(Lnet/minecraft/resources/ResourceLocation;)Ljava/lang/String;"))
    private static String read(ResourceLocation resourceId) {
        var resource = Minecraft.getInstance().getResourceManager().getResource(resourceId);
        if (resource.isEmpty()) return "";
        return StrictResourceText.read(resourceId.toString(), resource.get()::open);
    }
}
