package dev.abenli.mtrmemory;

import java.util.concurrent.CompletableFuture;
import com.mojang.blaze3d.vertex.VertexFormat;
import net.minecraft.resources.ResourceLocation;
import org.mtr.model.ModelLoaderBase;
import dev.abenli.mtrmemory.mixin.ModelLoaderAccess;

final class SharedBlockbenchLoader extends ModelLoaderBase {
    SharedBlockbenchLoader(ResourceLocation texture, CompletableFuture<ModelLoaderBase> source) {
        super(texture, VertexFormat.Mode.QUADS);
        source.thenAccept(loaded -> {
            ModelLoaderAccess data = (ModelLoaderAccess) loaded;
            data.meshes().forEach(this::addModel);
            data.displays().forEach(this::addModelDisplayParts);
            setModelLoaded();
        });
    }
}
