package site.benli06;

/** Provider equality is deliberately identity-based: equal paths can resolve different pack bytes. */
public final class ResourceSourceKey {
    private final Object provider;
    private final String path, texture;
    private final boolean flipV;
    public ResourceSourceKey(Object provider, String path, String texture, boolean flipV) {
        this.provider = provider; this.path = path; this.texture = texture; this.flipV = flipV;
    }
    @Override public boolean equals(Object other) {
        return other instanceof ResourceSourceKey key && provider == key.provider && path.equals(key.path)
                && texture.equals(key.texture) && flipV == key.flipV;
    }
    @Override public int hashCode() { return 31 * (31 * (31 * System.identityHashCode(provider) + path.hashCode()) + texture.hashCode()) + Boolean.hashCode(flipV); }
}
