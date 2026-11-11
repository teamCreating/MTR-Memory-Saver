package dev.abenli.mtrmemory.mixin;

import java.awt.Color;
import org.mtr.model.StoredVertexData;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(value = StoredVertexData.class, remap = false)
abstract class VertexColorMixin {
    @Redirect(method = "write", at = @At(value = "NEW", target = "java/awt/Color"))
    private static Color shareWhite(int red, int green, int blue, int alpha) {
        return red == 255 && green == 255 && blue == 255 && alpha == 255
                ? Color.WHITE : new Color(red, green, blue, alpha);
    }
}
