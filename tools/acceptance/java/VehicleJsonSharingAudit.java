package site.benli06.audit;

import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.ZipFile;
import site.benli06.VehicleJsonCache;
import org.mtr.core.serializer.*;
import org.mtr.core.tool.Utilities;
import org.mtr.libraries.com.google.gson.*;
import org.mtr.resource.*;

/** Compares shared inputs with native release readers and schema serialization. */
public final class VehicleJsonSharingAudit {
    private static int readersCompared;

    private static JsonObject serialize(SerializedDataBase data) {
        JsonObject value = new JsonObject();
        data.serializeFullData(new JsonWriter(value));
        return value;
    }

    private static SerializedDataBase configuration(String kind, JsonReader reader) {
        return switch (kind) {
            case "modelPropertiesResource" -> new ModelProperties(reader);
            case "positionDefinitionsResource" -> new PositionDefinitions(reader);
            default -> throw new AssertionError("Unknown audit kind: " + kind);
        };
    }

    private static void audit(String raw, String kind) throws Exception {
        JsonObject baseline = Utilities.parseJson(raw);
        JsonObject shared = VehicleJsonCache.parse(raw);
        if (!baseline.toString().equals(shared.toString())) throw new AssertionError("Parsed JSON changed");
        if (!shared.isEmpty() && VehicleJsonCache.parse(raw) != shared) throw new AssertionError("Identical JSON not shared");
        String before = shared.toString();
        JsonObject expected = serialize(configuration(kind, new JsonReader(baseline)));
        JsonReader first = new JsonReader(shared), second = new JsonReader(shared);
        Field mapField = JsonReader.class.getDeclaredField("map"); mapField.setAccessible(true);
        Object a = mapField.get(first), b = mapField.get(second);
        if (a == b) throw new AssertionError("Readers share mutable maps");
        for (JsonReader reader : List.of(first, second)) {
            JsonObject actual = serialize(configuration(kind, reader));
            if (!expected.toString().equals(actual.toString())) throw new AssertionError("Native schema serialization changed");
            readersCompared++;
        }
        if (!shared.toString().equals(before)) throw new AssertionError("Native consumers mutated shared JSON");
        if (!shared.isEmpty()) {
            String key = shared.entrySet().iterator().next().getKey();
            JsonObject override = new JsonObject(); override.addProperty(key, "reader-local-override");
            first.merge(new JsonReader(override));
            if (!serialize(configuration(kind, second)).toString().equals(expected.toString()))
                throw new AssertionError("Reader-local merge changed sibling configuration");
            if (!shared.toString().equals(before)) throw new AssertionError("Merge changed original JSON tree");
        }
    }

    public static void main(String[] args) throws Exception {
        JsonArray jobs = JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonArray();
        VehicleJsonCache.beginReload();
        int realInputs = 0;
        Map<String, ZipFile> archives = new HashMap<>();
        try {
            for (JsonElement element : jobs) {
                JsonObject job = element.getAsJsonObject();
                String archivePath = job.get("archive").getAsString();
                ZipFile archive = archives.get(archivePath);
                if (archive == null) { archive = new ZipFile(archivePath); archives.put(archivePath, archive); }
                byte[] bytes = archive.getInputStream(archive.getEntry(job.get("resource").getAsString())).readAllBytes();
                String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
                if (!hash.equals(job.get("sha256").getAsString())) throw new AssertionError("Audit input changed");
                audit(new String(bytes, StandardCharsets.UTF_8), job.get("kind").getAsString());
                realInputs++;
            }
        } finally { for (ZipFile archive : archives.values()) archive.close(); }
        for (String raw : List.of("{}", "", "null", "[]", "{", "{\"parts\":[{\"names\":[\"duplicate\",\"duplicate\"],\"type\":\"DISPLAY\"}],\"modelYOffset\":-0.0}")) {
            audit(raw, "modelPropertiesResource");
            audit(raw, "positionDefinitionsResource");
        }
        String raw = "{\"parts\":[{\"names\":[\"shared\"]}]}";
        JsonObject old = VehicleJsonCache.parse(raw);
        VehicleJsonCache.finishRegistration();
        JsonObject afterRelease = VehicleJsonCache.parse(raw);
        if (old == afterRelease || !old.toString().equals(afterRelease.toString())) throw new AssertionError("Released cache was reused");
        VehicleJsonCache.beginReload();
        JsonObject afterReload = VehicleJsonCache.parse(raw);
        if (afterRelease == afterReload || !old.toString().equals(afterReload.toString())) throw new AssertionError("Reload reused stale JSON");
        JsonObject report = new JsonObject();
        report.addProperty("real_configuration_inputs", realInputs);
        report.addProperty("native_readers_compared", readersCompared);
        report.addProperty("independent_reader_maps_and_merge_checked", true);
        report.addProperty("registration_release_and_reload_checked", true);
        report.addProperty("mismatches", 0);
        Files.writeString(Path.of(args[1]), new GsonBuilder().setPrettyPrinting().create().toJson(report) + "\n");
        System.out.println(report);
    }
}
