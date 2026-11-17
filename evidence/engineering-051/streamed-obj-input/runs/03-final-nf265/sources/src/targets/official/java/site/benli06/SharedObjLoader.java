package site.benli06;

import java.util.concurrent.CompletableFuture;
import com.mojang.blaze3d.vertex.VertexFormat;
import net.minecraft.resources.ResourceLocation;
import org.mtr.model.ModelLoaderBase;
import site.benli06.mixin.ModelLoaderAccess;

/** Independent native consumer; publication follows source and snapshot completion. */
final class SharedObjLoader extends ModelLoaderBase {
    private volatile Throwable failure;
    SharedObjLoader(ResourceLocation texture, CompletableFuture<ModelLoaderBase> source, String resourceId) {
        super(texture, VertexFormat.Mode.TRIANGLES);
        source.whenComplete((loaded, error) -> {
            synchronized (this) {
                if (error != null) { failed(resourceId, error); return; }
                try {
                    ((ModelLoaderAccess) loaded).meshes().forEach(this::addModel);
                    setModelLoaded();
                } catch (Throwable publication) { failed(resourceId, publication); }
            }
        });
    }
    private void failed(String resourceId, Throwable error) {
        failure = error;
        if (!(error instanceof java.util.concurrent.CancellationException))
            org.mtr.MTR.LOGGER.error("Shared OBJ loader failed for {}", resourceId, error);
    }
    public Throwable failure() { return failure; }
}
