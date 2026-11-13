package site.benli06;

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
}
