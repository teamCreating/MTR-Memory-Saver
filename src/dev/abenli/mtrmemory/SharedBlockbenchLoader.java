package dev.abenli.mtrmemory;

import java.util.concurrent.CompletableFuture;
import net.minecraft.class_293;
import net.minecraft.class_2960;
import org.mtr.model.ModelLoaderBase;
import dev.abenli.mtrmemory.mixin.ModelLoaderAccess;

final class SharedBlockbenchLoader extends ModelLoaderBase {
    SharedBlockbenchLoader(class_2960 texture, CompletableFuture<ModelLoaderBase> source) {
        super(texture, class_293.class_5596.field_27382);
        source.thenAccept(loaded -> {
            ModelLoaderAccess data = (ModelLoaderAccess) loaded;
            data.meshes().forEach(this::addModel);
            data.displays().forEach(this::addModelDisplayParts);
            setModelLoaded();
        });
    }
}
