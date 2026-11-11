package dev.abenli.mtrmemory.mixin;

import dev.abenli.mtrmemory.SegmentedResourceText;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import org.mtr.resource.ResourceManagerHelper;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

@Mixin(value = ResourceManagerHelper.class, remap = false)
abstract class SegmentedResourceTextMixin {
    @Redirect(method = "lambda$readResource$1([Ljava/lang/String;Lnet/minecraft/resources/ResourceLocation;Ljava/io/InputStream;)V",
            at = @At(value = "INVOKE", target = "Lorg/apache/commons/io/IOUtils;toString(Ljava/io/InputStream;Ljava/nio/charset/Charset;)Ljava/lang/String;"))
    private static String read(InputStream input, Charset charset) throws IOException {
        return SegmentedResourceText.read(input, charset);
    }
}
