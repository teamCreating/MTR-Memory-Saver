package site.benli06.probe;

import java.nio.file.Files;
import jdk.jfr.*;
import net.minecraft.client.Minecraft;
import net.neoforged.api.distmarker.Dist;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.client.event.RenderFrameEvent;
import net.neoforged.neoforge.event.tick.ServerTickEvent;

/** Observation only, installed exclusively in a copied performance instance. */
@Mod(value = "vehicle_performance_probe", dist = Dist.CLIENT)
public final class PerformanceProbe {
    private long previousFrame;
    private Tick tick;

    @Name("mtrtest.ClientFrame") @Label("Client render frame interval")
    @StackTrace(false) public static final class Frame extends Event {
        public double intervalMs;
        public boolean inWorld;
        public boolean paused;
        public String screen;
    }

    @Name("mtrtest.ServerTick") @Label("NeoForge server tick event span")
    @StackTrace(false) public static final class Tick extends Event {}

    public PerformanceProbe() {
        if (!Boolean.getBoolean("mtr.memory.acceptance")) throw new IllegalStateException("Enable the isolated acceptance probe with -Dmtr.memory.acceptance=true");
        NeoForge.EVENT_BUS.addListener(this::frame);
        NeoForge.EVENT_BUS.addListener(this::beforeTick);
        NeoForge.EVENT_BUS.addListener(this::afterTick);
    }

    private void frame(RenderFrameEvent.Pre ignored) {
        long now = System.nanoTime();
        if (previousFrame != 0) {
            Frame event = new Frame();
            if (event.isEnabled()) {
                var mc = Minecraft.getInstance();
                event.intervalMs = (now - previousFrame) / 1e6;
                event.inWorld = mc.level != null;
                event.paused = mc.isPaused();
                event.screen = mc.screen == null ? "game" : mc.screen.getClass().getName();
                event.commit();
            }
        }
        previousFrame = now;
    }

    private void beforeTick(ServerTickEvent.Pre ignored) {
        tick = new Tick();
        tick.begin();
    }

    private void afterTick(ServerTickEvent.Post ignored) {
        if (tick != null) {
            tick.end();
            tick.commit();
            tick = null;
        }
    }
}
