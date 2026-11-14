package dev.abenli.neutralprobe.mixin;

import org.mtr.client.MinecraftClientData;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(value = MinecraftClientData.class, remap = false)
public interface NativeClientDataAccess {
    @Accessor("instance")
    static MinecraftClientData neutralInstance() { throw new AssertionError("Native client accessor was not applied"); }
}
