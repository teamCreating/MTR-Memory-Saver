package site.benli06.audit;

import java.nio.file.*;
import java.io.*;
import java.util.Set;
import jdk.jfr.consumer.*;
import org.mtr.libraries.com.google.gson.*;

/** Stream a bounded projection; JFR's general JSON printer expands recursive type metadata. */
public final class ExportPerformanceJfr {
    public static void main(String[] args) throws Exception {
        Set<String> selected = Set.of("mtrtest.ClientFrame", "mtrtest.ServerTick", "jdk.ExecutionSample",
                "jdk.NativeMethodSample", "jdk.GarbageCollection", "jdk.GCPhasePause", "jdk.CPULoad",
                "jdk.GCHeapSummary", "jdk.ObjectAllocationSample", "jdk.VirtualThreadPinned");
        try (RecordingFile input = new RecordingFile(Path.of(args[0]));
             BufferedWriter output = Files.newBufferedWriter(Path.of(args[1]))) {
            output.write("{\"recording\":{\"events\":[");
            boolean first = true;
            while (input.hasMoreEvents()) {
                RecordedEvent event = input.readEvent();
                String type = event.getEventType().getName();
                if (!selected.contains(type)) continue;
                JsonObject value = new JsonObject();
                value.addProperty("startTime", event.getStartTime().toString());
                value.addProperty("duration", event.getDuration().toString());
                switch (type) {
                    case "mtrtest.ClientFrame" -> {
                        value.addProperty("intervalMs", event.getDouble("intervalMs"));
                        value.addProperty("inWorld", event.getBoolean("inWorld"));
                        value.addProperty("paused", event.getBoolean("paused"));
                        value.addProperty("screen", event.getString("screen"));
                    }
                    case "jdk.ExecutionSample", "jdk.NativeMethodSample" -> {
                        RecordedThread thread = event.getThread("sampledThread");
                        JsonObject threadJson = new JsonObject();
                        threadJson.addProperty("javaName", thread == null ? "" : thread.getJavaName());
                        value.add("sampledThread", threadJson);
                        JsonArray frames = new JsonArray();
                        RecordedStackTrace trace = event.getStackTrace();
                        if (trace != null) for (RecordedFrame frame : trace.getFrames()) {
                            JsonObject f = new JsonObject(), m = new JsonObject(), t = new JsonObject();
                            t.addProperty("name", frame.getMethod().getType().getName());
                            m.add("type", t);
                            m.addProperty("name", frame.getMethod().getName());
                            f.add("method", m);
                            frames.add(f);
                        }
                        JsonObject stack = new JsonObject();
                        stack.add("frames", frames);
                        stack.addProperty("truncated", trace != null && trace.isTruncated());
                        value.add("stackTrace", stack);
                    }
                    case "jdk.GarbageCollection" -> {
                        value.addProperty("name", event.getString("name"));
                        value.addProperty("cause", event.getString("cause"));
                        value.addProperty("sumOfPauses", event.getDuration("sumOfPauses").toString());
                    }
                    case "jdk.CPULoad" -> {
                        value.addProperty("jvmUser", event.getFloat("jvmUser"));
                        value.addProperty("jvmSystem", event.getFloat("jvmSystem"));
                        value.addProperty("machineTotal", event.getFloat("machineTotal"));
                    }
                    case "jdk.GCHeapSummary" -> {
                        value.addProperty("heapUsed", event.getLong("heapUsed"));
                        value.addProperty("when", event.getString("when"));
                    }
                    case "jdk.ObjectAllocationSample" -> {
                        JsonObject clazz = new JsonObject();
                        clazz.addProperty("name", event.getClass("objectClass").getName());
                        value.add("objectClass", clazz);
                        value.addProperty("weight", event.getLong("weight"));
                    }
                }
                JsonObject result = new JsonObject();
                result.addProperty("type", type);
                result.add("values", value);
                if (!first) output.write(',');
                first = false;
                output.write(result.toString());
            }
            output.write("]}}");
        }
    }
}
