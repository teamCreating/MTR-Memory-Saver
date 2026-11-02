package dev.abenli.mtrmemory.mixin;

import java.util.concurrent.ConcurrentHashMap;
import org.mtr.model.ModelLoaderBase;
import org.mtr.model.NewOptimizedModelGroup;
import org.mtr.render.StoredMatrixTransformations;
import org.mtr.libraries.it.unimi.dsi.fastutil.ints.IntIntImmutablePair;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectObjectImmutablePair;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(value = ModelLoaderBase.class, remap = false)
public interface ModelLoaderAccess {
    @Accessor("nameToNewOptimizedModelGroup")
    ConcurrentHashMap<String, NewOptimizedModelGroup> meshes();

    @Accessor("nameToRawModelDisplayParts")
    ConcurrentHashMap<String, ObjectArrayList<ObjectObjectImmutablePair<StoredMatrixTransformations, IntIntImmutablePair>>> displays();
}
