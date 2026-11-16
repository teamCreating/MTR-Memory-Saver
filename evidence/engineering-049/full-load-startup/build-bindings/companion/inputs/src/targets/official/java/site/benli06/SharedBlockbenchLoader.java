package site.benli06;

import java.util.Set;
import java.util.concurrent.CompletableFuture;
import com.mojang.blaze3d.vertex.VertexFormat;
import net.minecraft.resources.ResourceLocation;
import org.mtr.model.ModelLoaderBase;
import site.benli06.mixin.ModelLoaderAccess;

/** Each facade retains the display groups its property-dependent build can consume. */
final class SharedBlockbenchLoader extends ModelLoaderBase implements DisplayRetention.Loader {
    private Set<String> displayNames;
    private volatile Throwable failure;

    SharedBlockbenchLoader(ResourceLocation texture, CompletableFuture<ModelLoaderBase> source) {
        super(texture, VertexFormat.Mode.QUADS);
        source.whenComplete((loaded, error) -> {
            synchronized (this) {
                if (error != null) { failed(error); return; }
                try {
                ModelLoaderAccess data = (ModelLoaderAccess) loaded;
                data.meshes().forEach(this::addModel);
                data.displays().forEach((name, parts) -> {
                    if (displayNames == null || displayNames.contains(name)) addModelDisplayParts(name, parts);
                });
                setModelLoaded();
                } catch (Throwable publicationError) { failed(publicationError); }
            }
        });
    }

    private void failed(Throwable error) {
        failure = error;
        if (!(error instanceof java.util.concurrent.CancellationException))
            org.mtr.MTR.LOGGER.error("Shared Blockbench loader failed", error);
    }
    public Throwable failure() { return failure; }

    @Override public synchronized void selectDisplays(Set<String> names) {
        displayNames = Set.copyOf(names);
        DisplayRetention.retain(((ModelLoaderAccess) (Object) this).displays(), displayNames);
    }
}
