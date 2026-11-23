package site.benli06;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import org.mtr.Keys;
import org.mtr.resource.ResourceProvider;

/** The audited default provider reads the current ResourceManager unless native DEBUG is enabled. */
public final class NativeResourceSnapshots {
    private NativeResourceSnapshots() {}

    public static ResourceProvider wrap(ResourceProvider original) {
        return new SnapshotResourceProvider(original, NativeResourceSnapshots::open);
    }

    private static Optional<ResourceTextSnapshot> open(ResourceLocation resourceId) {
        // Native DEBUG has a separate local-file lookup and error policy. Keep its original get path.
        if (Keys.DEBUG) return Optional.empty();
        try (var scope = ReadAdmission.GLOBAL.open()) {
            var resource = Minecraft.getInstance().getResourceManager().getResource(resourceId);
            // The native provider returns empty text for a missing resource; parsing it still fails normally.
            return Optional.of(ResourceTextSnapshot.open(resource.isPresent() ? resource.get()::open
                    : () -> new ByteArrayInputStream(new byte[0]), StandardCharsets.UTF_8, ReadAdmission.GLOBAL));
        } catch (IOException error) { throw new UncheckedIOException(resourceId.toString(), error); }
    }
}
