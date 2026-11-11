package dev.abenli.mtrmemory;

import org.mtr.model.StoredVertexData;

/** Tests the exact float operations used by the audited release's immutable vertex transform. */
public final class VertexSharing {
    private VertexSharing() {}

    public static boolean unchanged(StoredVertexData vertex, double x, double y, double z, boolean mirror) {
        int factor = mirror ? -1 : 1;
        return same(vertex.x(), vertex.x() * factor + (float) x)
                && same(vertex.y(), vertex.y() + (float) y)
                && same(vertex.z(), vertex.z() * factor + (float) z)
                && same(vertex.normalX(), vertex.normalX() * factor)
                && same(vertex.normalZ(), vertex.normalZ() * factor);
        // Color, UV and normalY are passed through unchanged by the original method.
    }

    private static boolean same(float original, float transformed) {
        return Float.floatToRawIntBits(original) == Float.floatToRawIntBits(transformed);
    }
}
