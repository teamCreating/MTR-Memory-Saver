package site.benli06.probe;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.packs.PackLocationInfo;
import net.minecraft.server.packs.PackResources;
import net.minecraft.server.packs.PackType;
import net.minecraft.server.packs.metadata.MetadataSectionSerializer;
import net.minecraft.server.packs.repository.PackSource;
import net.minecraft.server.packs.resources.IoSupplier;
import net.minecraft.server.packs.resources.Resource;
import org.mtr.client.CustomResourceLoader;
import org.mtr.libraries.com.google.gson.JsonObject;
import site.benli06.ReadAdmission;

/** Scoped native Resource/stream fixtures; no interception remains after their owning test closes. */
public final class NativeResourceReadFixture {
    public enum Mode { OPEN_FAILURE, READ_FAILURE, CLOSE_FAILURE, OVERSIZED, EMPTY, MALFORMED_UTF8, MISSING, CORRECTED }
    public record Lookup(boolean intercepted, Optional<Resource> resource) {}
    private static final String NAMESPACE = "mtr_memory_acceptance";
    private static final ConcurrentHashMap<ResourceLocation, Fixture> ACTIVE = new ConcurrentHashMap<>();
    private static final AtomicLong NEXT = new AtomicLong();
    private static final byte[] MALFORMED = {(byte) 0xC3, 0x28, (byte) 0xF0, 0x28, (byte) 0x8C, 0x28, (byte) 0xFF};
    private static final PackResources PACK = new PackResources() {
        private final PackLocationInfo location = new PackLocationInfo("mtr_memory_acceptance-fixture",
                Component.literal("Strict resource acceptance fixture"), PackSource.DEFAULT, Optional.empty());
        @Override public IoSupplier<InputStream> getRootResource(String... path) { return null; }
        @Override public IoSupplier<InputStream> getResource(PackType type, ResourceLocation id) {
            Fixture fixture = ACTIVE.get(id);
            return fixture == null || fixture.mode == Mode.MISSING ? null : fixture::open;
        }
        @Override public void listResources(PackType type, String namespace, String path, ResourceOutput output) {}
        @Override public Set<String> getNamespaces(PackType type) { return Set.of(NAMESPACE); }
        @Override public <T> T getMetadataSection(MetadataSectionSerializer<T> serializer) { return null; }
        @Override public PackLocationInfo location() { return location; }
        @Override public void close() {}
    };

    private NativeResourceReadFixture() {}

    public static Fixture register(Mode mode, String correctedText) {
        if (!Boolean.getBoolean("mtr.memory.acceptance")) throw new IllegalStateException("Resource fixtures require isolated acceptance mode");
        ResourceLocation id = ResourceLocation.fromNamespaceAndPath(NAMESPACE,
                "strict/" + mode.name().toLowerCase(Locale.ROOT) + "_" + NEXT.incrementAndGet() + ".bbmodel");
        Fixture fixture = new Fixture(id, mode, correctedText.getBytes(StandardCharsets.UTF_8));
        if (ACTIVE.putIfAbsent(id, fixture) != null) throw new IllegalStateException("Resource fixture identity collision");
        return fixture;
    }

    /** Only exact currently registered test identities are intercepted; every other lookup delegates. */
    public static Lookup lookup(ResourceLocation id) {
        Fixture fixture = Boolean.getBoolean("mtr.memory.acceptance") ? ACTIVE.get(id) : null;
        if (fixture == null) return new Lookup(false, Optional.empty());
        fixture.lookups.incrementAndGet();
        return new Lookup(true, fixture.mode == Mode.MISSING ? Optional.empty() : Optional.of(new Resource(PACK, fixture::open)));
    }

    public static String readActual(ResourceLocation id) {
        try {
            var method = CustomResourceLoader.class.getDeclaredMethod("readResource", ResourceLocation.class);
            method.setAccessible(true);
            return (String) method.invoke(null, id);
        } catch (InvocationTargetException error) {
            if (error.getCause() instanceof RuntimeException failure) throw failure;
            if (error.getCause() instanceof Error failure) throw failure;
            throw new IllegalStateException("Native resource reader failed", error.getCause());
        } catch (ReflectiveOperationException error) { throw new IllegalStateException(error); }
    }

    public static int active() { return ACTIVE.size(); }
    public static String malformedReplacement() { return new String(MALFORMED, StandardCharsets.UTF_8); }

    public static final class Fixture implements AutoCloseable {
        public final ResourceLocation id;
        private volatile Mode mode;
        private final byte[] corrected;
        private final AtomicLong lookups = new AtomicLong(), opens = new AtomicLong(), reads = new AtomicLong(), closes = new AtomicLong(), bytes = new AtomicLong();
        private Fixture(ResourceLocation id, Mode mode, byte[] corrected) { this.id = id; this.mode = mode; this.corrected = corrected; }
        public void correct() { mode = Mode.CORRECTED; }
        public long lookups() { return lookups.get(); }
        public long opens() { return opens.get(); }
        public long closes() { return closes.get(); }
        public long bytesRead() { return bytes.get(); }
        private InputStream open() throws IOException {
            opens.incrementAndGet();
            Mode observed = mode;
            if (observed == Mode.OPEN_FAILURE) throw new FaultIOException(observed, id);
            byte[] payload = observed == Mode.EMPTY ? new byte[0] : observed == Mode.MALFORMED_UTF8 ? MALFORMED : corrected;
            long length = observed == Mode.OVERSIZED ? Math.addExact(ReadAdmission.GLOBAL.maxCodeUnits(), 1) : payload.length;
            return new InputStream() {
                private long position;
                private boolean closed;
                @Override public int read() throws IOException {
                    reads.incrementAndGet(); checkReadable();
                    if (position == length) return -1;
                    int value = observed == Mode.OVERSIZED ? 'a' : payload[(int) position] & 255;
                    position++; bytes.incrementAndGet();
                    return value;
                }
                @Override public int read(byte[] output, int offset, int count) throws IOException {
                    java.util.Objects.checkFromIndexSize(offset, count, output.length);
                    reads.incrementAndGet(); checkReadable();
                    if (count == 0) return 0;
                    if (position == length) return -1;
                    int copied = (int) Math.min(count, length - position);
                    if (observed == Mode.OVERSIZED) Arrays.fill(output, offset, offset + copied, (byte) 'a');
                    else System.arraycopy(payload, (int) position, output, offset, copied);
                    position += copied; bytes.addAndGet(copied);
                    return copied;
                }
                private void checkReadable() throws IOException {
                    if (closed) throw new IOException("Fixture stream already closed");
                    if (observed == Mode.READ_FAILURE) throw new FaultIOException(observed, id);
                }
                @Override public void close() throws IOException {
                    closes.incrementAndGet(); closed = true;
                    if (observed == Mode.CLOSE_FAILURE) throw new FaultIOException(observed, id);
                }
            };
        }
        public JsonObject observations() {
            JsonObject value = new JsonObject();
            value.addProperty("resource", id.toString()); value.addProperty("mode", mode.name());
            value.addProperty("lookups", lookups()); value.addProperty("opens", opens());
            value.addProperty("read_calls", reads.get()); value.addProperty("closes", closes());
            value.addProperty("bytes_read", bytesRead()); value.addProperty("resource_source", PACK.packId());
            return value;
        }
        @Override public void close() { ACTIVE.remove(id, this); }
    }

    public static final class FaultIOException extends IOException {
        public final Mode phase;
        private FaultIOException(Mode phase, ResourceLocation id) { super(id + ": " + phase); this.phase = phase; }
    }
}
