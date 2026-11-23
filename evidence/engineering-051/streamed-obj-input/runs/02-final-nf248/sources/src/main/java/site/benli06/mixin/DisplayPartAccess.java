package site.benli06.mixin;

import org.mtr.generated.resource.ModelPropertiesPartSchema;
import org.mtr.resource.PartType;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.ObjectArrayList;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(value = ModelPropertiesPartSchema.class, remap = false)
public interface DisplayPartAccess {
    @Accessor("type") PartType partType();
    @Accessor("names") ObjectArrayList<String> partNames();
}
