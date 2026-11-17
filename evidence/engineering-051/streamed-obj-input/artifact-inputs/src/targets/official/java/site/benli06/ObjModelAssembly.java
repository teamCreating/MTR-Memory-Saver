package site.benli06;

import java.util.function.Function;
import net.minecraft.resources.ResourceLocation;
import org.mtr.libraries.de.javagl.obj.Obj;
import org.mtr.libraries.de.javagl.obj.Mtl;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap;

/** Typed input to the audited native OBJ mesh builder. */
public interface ObjModelAssembly {
    void assemble(Obj obj, Object2ObjectOpenHashMap<String, Mtl> materials,
                  Function<String, ResourceLocation> textures, boolean flipV);
}
