package site.benli06;

import java.util.function.Consumer;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.phys.AABB;
import org.mtr.model.StoredVertexData;
import org.mtr.resource.RenderStage;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;

public final class PackedModelGroupOperations {
    private PackedModelGroupOperations() {}

    public static void add(PackedModelGroupStore<ResourceLocation> store, ObjectArrayList<AABB> boxes,
                           RenderStage stage, ResourceLocation texture,
                           Consumer<ObjectArrayList<StoredVertexData>> consumer, ObjectArrayList<AABB> suppliedBoxes) {
        ObjectArrayList<StoredVertexData> vertices = new ObjectArrayList<>();
        consumer.accept(vertices);
        store.add(stage, texture, vertices);
        if (suppliedBoxes == null) {
            double[] bounds = {Float.MAX_VALUE, Float.MAX_VALUE, Float.MAX_VALUE,
                    -Float.MAX_VALUE, -Float.MAX_VALUE, -Float.MAX_VALUE};
            vertices.forEach(v -> {
                bounds[0] = Math.min(bounds[0], v.x()); bounds[1] = Math.min(bounds[1], v.y());
                bounds[2] = Math.min(bounds[2], v.z()); bounds[3] = Math.max(bounds[3], v.x());
                bounds[4] = Math.max(bounds[4], v.y()); bounds[5] = Math.max(bounds[5], v.z());
            });
            boxes.add(new AABB(bounds[0], bounds[1], bounds[2], bounds[3], bounds[4], bounds[5]));
        } else boxes.addAll(suppliedBoxes);
    }
}
