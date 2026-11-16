package dev.abenli.neutralprobe;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Path;
import java.nio.file.Files;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

final class FrameEventTest {
    @TempDir Path temporary;
    @Test void frameAndTickEventsHaveReadableIndependentJfrSchemas() throws Exception {
        String retained = System.getProperty("neutralProbeJfrOutput");
        Path output = retained == null ? temporary.resolve("events.jfr") : Path.of(retained);
        Files.createDirectories(output.getParent());
        try (var recording = new Recording()) {
            recording.enable("mtrtest.ClientFrame").withoutThreshold();
            recording.enable("mtrtest.ServerTick").withoutThreshold();
            recording.start();
            var frame = new NativeObserver.Frame();
            assertTrue(frame.isEnabled());
            frame.intervalMs = 12.5; frame.inWorld = true; frame.paused = false; frame.screen = "game";
            frame.commit();
            var tick = new NativeObserver.Tick();
            tick.begin(); tick.end(); tick.commit();
            recording.stop(); recording.dump(output);
        }
        var events = RecordingFile.readAllEvents(output);
        var frame = events.stream().filter(event -> event.getEventType().getName().equals("mtrtest.ClientFrame")).findFirst().orElseThrow();
        assertEquals(12.5, frame.getDouble("intervalMs"));
        assertTrue(frame.getBoolean("inWorld"));
        assertFalse(frame.getBoolean("paused"));
        assertEquals("game", frame.getString("screen"));
        assertTrue(events.stream().anyMatch(event -> event.getEventType().getName().equals("mtrtest.ServerTick")));
    }
}
