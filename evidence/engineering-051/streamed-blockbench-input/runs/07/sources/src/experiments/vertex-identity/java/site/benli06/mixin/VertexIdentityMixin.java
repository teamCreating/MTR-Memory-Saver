package site.benli06.mixin;

import site.benli06.VertexSharing;
import org.mtr.model.StoredVertexData;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = StoredVertexData.class, remap = false)
abstract class VertexIdentityMixin {
    @Inject(method = "modify", at = @At("HEAD"), cancellable = true)
    private void reuseUnchanged(double x, double y, double z, boolean mirror,
                               CallbackInfoReturnable<StoredVertexData> callback) {
        StoredVertexData vertex = (StoredVertexData) (Object) this;
        if (VertexSharing.unchanged(vertex, x, y, z, mirror)) callback.setReturnValue(vertex);
    }
}
