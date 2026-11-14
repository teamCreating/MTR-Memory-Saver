package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import site.benli06.audit.DisplayRetentionAudit;
import site.benli06.audit.PackedMeshAudit;
import site.benli06.audit.VehicleJsonSharingAudit;

/** Calls native MTR methods without installing Mixins or creating GPU models. */
@Timeout(60)
class NativeAlgorithmAuditTest {
    @TempDir Path temporary;
    @Test void packedCoordinatesEmissionBoundsAndMergeMatchNative() throws Exception {
        PackedMeshAudit.main(new String[] {temporary.resolve("packed.json").toString()});
    }
    @Test void displaySelectionMatchesNativePartCache() throws Exception {
        DisplayRetentionAudit.main(new String[] {temporary.resolve("displays.json").toString()});
    }
    @Test void vehicleJsonKeepsNativeReadersAndReaderLocalMerge() throws Exception {
        Path jobs = temporary.resolve("jobs.json"); Files.writeString(jobs, "[]");
        VehicleJsonSharingAudit.main(new String[] {jobs.toString(), temporary.resolve("json.json").toString()});
    }
    @Test void malformedBlockbenchInputsCannotBecomeSuccessfulEmptyModels() {
        for (String raw : new String[]{"", "{", "[]", "null", "{\"elements\":["})
            assertThrows(RuntimeException.class, () -> SharedBlockbenchCache.parseInput(raw), raw);
    }
    @Test void validBlockbenchInputsKeepNativeSchemaSerialization() {
        for (String raw : new String[]{"{}", "{\"meta\":{\"format_version\":\"4.10\"},\"resolution\":{\"width\":32,\"height\":16},\"elements\":[],\"outliner\":[],\"textures\":[]}"}) {
            var expected = new org.mtr.resource.BlockbenchModel(new org.mtr.core.serializer.JsonReader(org.mtr.core.tool.Utilities.parseJson(raw)));
            var actual = SharedBlockbenchCache.parseInput(raw);
            var expectedJson = new org.mtr.libraries.com.google.gson.JsonObject();
            var actualJson = new org.mtr.libraries.com.google.gson.JsonObject();
            expected.serializeFullData(new org.mtr.core.serializer.JsonWriter(expectedJson));
            actual.serializeFullData(new org.mtr.core.serializer.JsonWriter(actualJson));
            assertEquals(expectedJson, actualJson);
        }
    }
}
