package dev.abenli.mtrmemory;

import java.util.Set;
import java.util.concurrent.CompletableFuture;
import com.mojang.blaze3d.vertex.VertexFormat;
import net.minecraft.resources.ResourceLocation;
import org.mtr.model.ModelLoaderBase;
import dev.abenli.mtrmemory.mixin.ModelLoaderAccess;

/** Each facade retains the display groups its property-dependent build can consume. */
final class SharedBlockbenchLoader extends ModelLoaderBase implements DisplayRetention.Loader {
    private Set<String> displayNames;

    SharedBlockbenchLoader(ResourceLocation texture, CompletableFuture<ModelLoaderBase> source) {
        super(texture, VertexFormat.Mode.QUADS);
        source.thenAccept(loaded -> {
            synchronized (this) {
                ModelLoaderAccess data = (ModelLoaderAccess) loaded;
                data.meshes().forEach(this::addModel);
                data.displays().forEach((name, parts) -> {
                    if (displayNames == null || displayNames.contains(name)) addModelDisplayParts(name, parts);
                });
                setModelLoaded();
            }
        });
    }

    @Override public synchronized void selectDisplays(Set<String> names) {
        displayNames = Set.copyOf(names);
        DisplayRetention.retain(((ModelLoaderAccess) (Object) this).displays(), displayNames);
    }
}
