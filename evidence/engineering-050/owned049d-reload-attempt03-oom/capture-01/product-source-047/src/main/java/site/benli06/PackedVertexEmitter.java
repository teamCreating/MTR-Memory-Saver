package site.benli06;

import com.mojang.blaze3d.vertex.VertexConsumer;
import net.minecraft.client.renderer.texture.OverlayTexture;
import org.mtr.data.IGui;

public final class PackedVertexEmitter {
    private PackedVertexEmitter() {}

    public static void emit(PackedVertices vertices, VertexConsumer consumer) {
        vertices.emit((x, y, z, color, u, v, nx, ny, nz) -> consumer.addVertex(
                x, y, z, color, u, v, OverlayTexture.NO_OVERLAY, IGui.DEFAULT_LIGHT, nx, ny, nz));
    }
}
