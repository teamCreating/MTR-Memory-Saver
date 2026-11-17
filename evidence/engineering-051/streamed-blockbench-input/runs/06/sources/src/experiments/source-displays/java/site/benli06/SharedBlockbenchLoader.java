package site.benli06;

import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.function.Function;
import com.mojang.blaze3d.vertex.VertexFormat;
import net.minecraft.resources.ResourceLocation;
import org.mtr.model.ModelLoaderBase;
import site.benli06.mixin.ModelLoaderAccess;

/** Vehicle sources start after property selection; object/rail sources keep eager behavior. */
final class SharedBlockbenchLoader extends ModelLoaderBase implements DisplayRetention.Loader {
    private final Function<Set<String>, CompletableFuture<ModelLoaderBase>> factory;
    private Set<String> displayNames, submittedNames;
    private int generation;

    SharedBlockbenchLoader(ResourceLocation texture, CompletableFuture<ModelLoaderBase> source) {
        super(texture, VertexFormat.Mode.QUADS); factory = null; bind(source, ++generation);
    }

    SharedBlockbenchLoader(ResourceLocation texture, Function<Set<String>, CompletableFuture<ModelLoaderBase>> factory) {
        super(texture, VertexFormat.Mode.QUADS); this.factory = factory;
    }

    private void bind(CompletableFuture<ModelLoaderBase> source, int expectedGeneration) {
        source.thenAccept(loaded -> {
            synchronized (this) {
                if (generation != expectedGeneration) return;
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
        ModelLoaderAccess self = (ModelLoaderAccess) (Object) this;
        if (factory != null && !displayNames.equals(submittedNames)) {
            submittedNames = displayNames;
            int next = ++generation;
            reset(); self.meshes().clear(); self.displays().clear();
            bind(factory.apply(displayNames), next);
        } else DisplayRetention.retain(self.displays(), displayNames);
    }
}
