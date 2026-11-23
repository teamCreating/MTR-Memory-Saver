package site.benli06;

import java.util.Objects;
import java.util.Optional;
import net.minecraft.resources.ResourceLocation;
import org.mtr.resource.ResourceProvider;

/** Explicit capability installed only at the audited native provider construction sites. */
public final class SnapshotResourceProvider implements ResourceProvider {
    @FunctionalInterface public interface Opener {
        Optional<ResourceTextSnapshot> open(ResourceLocation resource);
    }
    private final ResourceProvider delegate;
    private final Opener opener;
    public SnapshotResourceProvider(ResourceProvider delegate, Opener opener) {
        this.delegate = Objects.requireNonNull(delegate); this.opener = Objects.requireNonNull(opener);
    }
    @Override public String get(ResourceLocation resource) { return delegate.get(resource); }
    public ResourceProvider delegate() { return delegate; }
    public Optional<ResourceTextSnapshot> snapshot(ResourceLocation resource) { return opener.open(resource); }
}
