package dev.abenli.mtrmemory.mixin;

import com.mojang.blaze3d.vertex.VertexFormat;
import dev.abenli.mtrmemory.*;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.phys.AABB;
import org.mtr.model.*;
import org.mtr.resource.RenderStage;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;
import org.spongepowered.asm.mixin.*;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.*;
import java.util.function.Consumer;

@Mixin(value = NewOptimizedModelGroup.class, remap = false)
abstract class PackedModelGroupMixin implements PackedModelGroupAccess<ResourceLocation> {
    @Shadow @Final public ObjectArrayList<AABB> boxes;
    @Unique private final PackedModelGroupStore<ResourceLocation> mtrMemory$meshes = new PackedModelGroupStore<>();

    public PackedModelGroupStore<ResourceLocation> packedMeshStore() { return mtrMemory$meshes; }

    @Inject(method = "add", at = @At("HEAD"), cancellable = true)
    private void pack(RenderStage stage, ResourceLocation texture, Consumer<ObjectArrayList<StoredVertexData>> consumer,
                      ObjectArrayList<AABB> suppliedBoxes, CallbackInfo callback) {
        PackedModelGroupOperations.add(mtrMemory$meshes, boxes, stage, texture, consumer, suppliedBoxes);
        callback.cancel();
    }

    @Inject(method = "merge", at = @At("HEAD"), cancellable = true)
    private void mergePacked(NewOptimizedModelGroup source, RenderStage defaultStage,
                             double x, double y, double z, boolean flip, CallbackInfo callback) {
        @SuppressWarnings("unchecked")
        var packed = (PackedModelGroupAccess<ResourceLocation>) (Object) source;
        mtrMemory$meshes.merge(packed.packedMeshStore(), defaultStage, x, y, z, flip);
        callback.cancel();
    }

    @Inject(method = "build", at = @At("HEAD"), cancellable = true)
    private void buildPacked(VertexFormat.Mode mode,
                             CallbackInfoReturnable<Object2ObjectOpenHashMap<RenderStage, ObjectArrayList<NewOptimizedModel>>> callback) {
        Object2ObjectOpenHashMap<RenderStage, ObjectArrayList<NewOptimizedModel>> models = new Object2ObjectOpenHashMap<>(RenderStage.values().length);
        mtrMemory$meshes.groups().forEach((stage, textures) -> {
            if (stage != null) textures.forEach((texture, vertices) -> models
                    .computeIfAbsent(stage, key -> new ObjectArrayList<>())
                    .add(new NewOptimizedModel(texture, mode, vertices.size() == 0 ? null :
                            consumer -> PackedVertexEmitter.emit(vertices, consumer))));
        });
        callback.setReturnValue(models);
    }
}
