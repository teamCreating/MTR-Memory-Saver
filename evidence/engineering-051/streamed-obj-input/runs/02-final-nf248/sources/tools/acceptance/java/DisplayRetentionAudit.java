package site.benli06.audit;

import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import java.awt.Color;
import site.benli06.DisplayRetention;
import org.mtr.core.serializer.JsonReader;
import org.mtr.libraries.com.google.gson.*;
import org.mtr.libraries.it.unimi.dsi.fastutil.ints.IntIntImmutablePair;
import org.mtr.libraries.it.unimi.dsi.fastutil.objects.*;
import org.mtr.model.*;
import org.mtr.render.StoredMatrixTransformations;
import org.mtr.resource.*;
import net.minecraft.world.phys.AABB;

/** Compares retention with the unmodified release's actual part-cache consumer. */
public final class DisplayRetentionAudit {
    private record Result(Object2ObjectOpenHashMap<PartCondition, NewOptimizedModelGroup> meshes,
                          ObjectArrayList<ModelPropertiesPart.RawDoorModelDetails> doors,
                          Object2ObjectOpenHashMap<PartCondition, ObjectArrayList<ModelDisplayPart>> displays,
                          ObjectArrayList<AABB> floors, ObjectArrayList<AABB> doorways) {}

    private static Result build(ModelPropertiesPart part,
            java.util.concurrent.ConcurrentHashMap<String, NewOptimizedModelGroup> meshes,
            java.util.concurrent.ConcurrentHashMap<String, ObjectArrayList<ObjectObjectImmutablePair<StoredMatrixTransformations, IntIntImmutablePair>>> displays,
            PositionDefinitions positions) {
        Result value = new Result(new Object2ObjectOpenHashMap<>(), new ObjectArrayList<>(),
                new Object2ObjectOpenHashMap<>(), new ObjectArrayList<>(), new ObjectArrayList<>());
        part.writeCache(meshes, displays, positions, value.meshes, value.doors,
                value.displays, value.floors, value.doorways, 0.125);
        return value;
    }

    private static void equalFields(Object left, Object right) throws Exception {
        if (left.getClass() != right.getClass()) throw new AssertionError("Classes differ");
        for (Field field : left.getClass().getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers())) continue;
            field.setAccessible(true);
            if (!Objects.equals(field.get(left), field.get(right)))
                throw new AssertionError("Display field differs: " + field.getName());
        }
    }

    public static void main(String[] args) throws Exception {
        var meshes = new java.util.concurrent.ConcurrentHashMap<String, NewOptimizedModelGroup>();
        var displays = new java.util.concurrent.ConcurrentHashMap<String, ObjectArrayList<ObjectObjectImmutablePair<StoredMatrixTransformations, IntIntImmutablePair>>>();
        for (String name : List.of("body", "screen", "shared", "unused")) {
            var group = new NewOptimizedModelGroup();
            group.add(RenderStage.INTERIOR_TRANSLUCENT, null, list -> list.add(
                    PackedMeshAudit.createVertex(-0.0F, 1, -2, Color.WHITE, 0.25F, 0.75F, 0, 0, 1)), null);
            meshes.put(name, group);
            var parts = new ObjectArrayList<ObjectObjectImmutablePair<StoredMatrixTransformations, IntIntImmutablePair>>();
            parts.add(new ObjectObjectImmutablePair<>(new StoredMatrixTransformations(1, 2, 3), new IntIntImmutablePair(12, 8)));
            displays.put(name, parts);
        }
        PositionDefinitions positions = new PositionDefinitions(new JsonReader(JsonParser.parseString(
                "{\"positionDefinitions\":[{\"name\":\"anchor\",\"positions\":[{\"x\":2,\"y\":3,\"z\":4}],\"positionsFlipped\":[{\"x\":-2,\"y\":-3,\"z\":-4}]}]}")));
        int checked = 0, displayInstances = 0;
        for (PartType type : PartType.values()) {
            for (boolean door : new boolean[]{false, true}) {
                JsonObject json = new JsonObject();
                JsonArray names = new JsonArray();
                names.add("body"); names.add("screen"); names.add("shared"); names.add("screen"); names.add("missing");
                json.add("names", names);
                JsonArray anchors = new JsonArray(); anchors.add("anchor"); anchors.add("");
                json.add("positionDefinitions", anchors);
                json.addProperty("type", type.name());
                json.addProperty("doorXMultiplier", door ? 1 : 0);
                ModelPropertiesPart part = new ModelPropertiesPart(new JsonReader(json));
                var selected = new java.util.concurrent.ConcurrentHashMap<>(displays);
                DisplayRetention.retain(selected, type == PartType.DISPLAY ? Set.of("body", "screen", "shared", "missing") : Set.of());
                if (selected.containsKey("unused") || displays.size() != 4) throw new AssertionError("Source was changed");
                selected.forEach((name, value) -> { if (value != displays.get(name)) throw new AssertionError("Display data was copied"); });
                Result before = build(part, meshes, displays, positions);
                Result after = build(part, meshes, selected, positions);
                if (!before.floors.equals(after.floors) || !before.doorways.equals(after.doorways)
                        || before.doors.size() != after.doors.size() || !before.meshes.keySet().equals(after.meshes.keySet())
                        || !before.displays.keySet().equals(after.displays.keySet())) throw new AssertionError("Native cache changed");
                for (PartCondition condition : before.displays.keySet()) {
                    var a = before.displays.get(condition); var b = after.displays.get(condition);
                    if (a.size() != b.size()) throw new AssertionError("Display multiplicity changed");
                    for (int i = 0; i < a.size(); i++) { equalFields(a.get(i), b.get(i)); displayInstances++; }
                }
                checked++;
            }
        }
        if (displayInstances == 0) throw new AssertionError("No actual display instances compared");
        String report = "{\"release_part_cases\":" + checked + ",\"display_instances_compared\":" + displayInstances
                + ",\"source_unchanged\":true,\"mismatches\":0}";
        Files.writeString(Path.of(args[0]), report + "\n");
        System.out.println(report);
    }
}
