package dev.abenli.neutralprobe.mixin;

import org.mtr.libraries.it.unimi.dsi.fastutil.ints.Int2ObjectAVLTreeMap;
import org.mtr.resource.VehicleResource;
import org.mtr.resource.VehicleResourceCache;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(value = VehicleResource.class, remap = false)
public interface VehicleCacheAccess {
    @Accessor("vehicleResourceCacheByCarNumberAndTotalCars")
    Int2ObjectAVLTreeMap<Int2ObjectAVLTreeMap<VehicleResourceCache>> neutralExistingCaches();
}
