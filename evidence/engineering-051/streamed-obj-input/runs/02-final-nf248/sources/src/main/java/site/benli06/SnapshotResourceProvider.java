package site.benli06;

import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.resources.ResourceLocation;
import org.mtr.resource.ResourceProvider;

/** Explicit capability installed only at the audited native provider construction sites. */
public final class SnapshotResourceProvider implements ResourceProvider {
    public record Statistics(long attempts, long captures, long stringFallbacks, long failures, long decodedCodeUnits) {}
    private static final class Counts {
        final AtomicLong attempts = new AtomicLong(), captures = new AtomicLong(), stringFallbacks = new AtomicLong(),
                failures = new AtomicLong(), decodedCodeUnits = new AtomicLong();
    }
    private static volatile Counts current = new Counts();
    @FunctionalInterface public interface Opener {
        Optional<ResourceTextSnapshot> open(ResourceLocation resource);
    }
    private final ResourceProvider delegate;
    private final Opener opener;
    private final Counts counts = current;
    public SnapshotResourceProvider(ResourceProvider delegate, Opener opener) {
        this.delegate = Objects.requireNonNull(delegate); this.opener = Objects.requireNonNull(opener);
    }
    @Override public String get(ResourceLocation resource) { return delegate.get(resource); }
    public ResourceProvider delegate() { return delegate; }
    public Optional<ResourceTextSnapshot> snapshot(ResourceLocation resource) {
        counts.attempts.incrementAndGet();
        try {
            var result = opener.open(resource);
            if (result.isPresent()) {
                counts.captures.incrementAndGet(); counts.decodedCodeUnits.addAndGet(result.get().length());
            } else counts.stringFallbacks.incrementAndGet();
            return result;
        } catch (Throwable error) { counts.failures.incrementAndGet(); throw error; }
    }
    static void beginReload() { current = new Counts(); }
    public static Statistics statistics() {
        Counts counts = current;
        return new Statistics(counts.attempts.get(), counts.captures.get(), counts.stringFallbacks.get(),
                counts.failures.get(), counts.decodedCodeUnits.get());
    }
}
