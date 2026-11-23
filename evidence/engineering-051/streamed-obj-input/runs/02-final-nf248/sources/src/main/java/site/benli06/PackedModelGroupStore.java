package site.benli06;

import java.util.List;
import org.mtr.model.StoredVertexData;
import org.mtr.resource.RenderStage;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;

/** Preserves the release's stage/texture grouping and insertion semantics. */
public final class PackedModelGroupStore<T> {
    private final Object2ObjectOpenHashMap<RenderStage, Object2ObjectOpenHashMap<T, PackedVertices>> groups = new Object2ObjectOpenHashMap<>();

    public Object2ObjectOpenHashMap<RenderStage, Object2ObjectOpenHashMap<T, PackedVertices>> groups() { return groups; }

    public void add(RenderStage stage, T texture, List<StoredVertexData> vertices) {
        groups.computeIfAbsent(stage, key -> new Object2ObjectOpenHashMap<>())
                .computeIfAbsent(texture, key -> new PackedVertices()).append(vertices);
    }

    public void merge(PackedModelGroupStore<T> source, RenderStage defaultStage,
                      double x, double y, double z, boolean flip) {
        source.groups.forEach((stage, textures) -> {
            RenderStage targetStage = stage == null ? defaultStage : stage;
            textures.forEach((texture, vertices) -> {
                // The original creates destination entries inside its per-vertex loop.
                if (vertices.size() != 0) groups.computeIfAbsent(targetStage, key -> new Object2ObjectOpenHashMap<>())
                        .computeIfAbsent(texture, key -> new PackedVertices()).appendTransformed(vertices, x, y, z, flip);
            });
        });
    }
}
