package dev.abenli.neutralprobe.mixin;

import java.util.concurrent.atomic.AtomicInteger;
import org.mtr.model.ModelLoaderBase;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

@Mixin(value = ModelLoaderBase.class, remap = false)
public interface NativePendingAccess {
    @Accessor("PENDING_PARSE_COUNT")
    static AtomicInteger neutralPending() { throw new AssertionError("Native pending accessor was not applied"); }
}
