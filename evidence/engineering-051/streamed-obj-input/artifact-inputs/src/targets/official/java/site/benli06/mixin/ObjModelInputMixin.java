package site.benli06.mixin;

import java.util.function.Function;
import com.mojang.blaze3d.vertex.VertexFormat;
import net.minecraft.resources.ResourceLocation;
import org.mtr.model.ModelLoaderBase;
import org.mtr.model.ObjModelLoader;
import org.mtr.model.NewOptimizedModelGroup;
import org.mtr.libraries.de.javagl.obj.Obj;
import org.mtr.libraries.de.javagl.obj.Mtl;
import org.mtr.libraries.de.javagl.obj.ObjSplitting;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;
import site.benli06.ObjModelAssembly;

@Mixin(value = ObjModelLoader.class, remap = false)
abstract class ObjModelInputMixin extends ModelLoaderBase implements ObjModelAssembly {
    protected ObjModelInputMixin(ResourceLocation texture, VertexFormat.Mode mode) { super(texture, mode); }

    @Invoker("loadModel")
    protected abstract NewOptimizedModelGroup buildNative(Obj obj, Object2ObjectOpenHashMap<String, Mtl> materials,
                                                          Function<String, ResourceLocation> textures, boolean flipV);

    @Override public void assemble(Obj obj, Object2ObjectOpenHashMap<String, Mtl> materials,
                                   Function<String, ResourceLocation> textures, boolean flipV) {
        if (!canLoadModel()) throw new IllegalStateException("OBJ source was already loaded");
        // VehicleModel's audited OBJ factory always requests splitModel=true.
        ObjSplitting.splitByGroups(obj).forEach((name, group) -> addModel(name, buildNative(group, materials, textures, flipV)));
        setModelLoaded();
    }
}
