package site.benli06.mixin;

import site.benli06.DisplayRetention;
import org.mtr.core.serializer.ReaderBase;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ModelProperties;
import org.mtr.resource.VehicleModel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(value = VehicleModel.class, remap = false)
abstract class DisplaySelectionMixin {
    @Shadow @Final private ModelLoaderBase modelLoaderBase;

    @Redirect(method = "createModelSupplier", at = @At(value = "NEW", target = "org/mtr/resource/ModelProperties"))
    private ModelProperties selectDisplays(ReaderBase reader) {
        ModelProperties properties = new ModelProperties(reader);
        DisplayRetention.configure(modelLoaderBase, properties);
        return properties;
    }
}
