package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

/** Exercises snapshot operations through the ordinary java.nio Files API. */
@Timeout(10)
class SnapshotFilesystemFailureTest {
    @TempDir Path directory;
    private static final String TEXT = "a".repeat(15000) + "🚆\u0000\u03b1";

    @Test void outputWriteFailureCannotPublishSuccessfulTextAndSamePathRetries() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.WRITE);
        var admission = new ReadAdmission(2, 20000);
        var cache = new BoundedTextCache(100000, admission);
        var failure = assertThrows(UncheckedIOException.class,
                () -> cache.get("source", ignored -> decoded(filesystem, admission)));
        assertSame(filesystem.writeFailure, failure.getCause());
        assertTrue(filesystem.outputWrites > 0);
        assertEquals(0, cache.statistics()[0]);
        assertEquals(0, cache.activity()[6]);
        settled(admission); assertEquals(0, files());
        filesystem.fault = SnapshotFaultFileSystem.Fault.NONE;
        assertEquals(TEXT, cache.get("source", ignored -> decoded(filesystem, admission)));
        assertEquals(TEXT, cache.get("source", ignored -> fail("Successful retry was not cached")));
        settled(admission); assertEquals(0, files());
    }

    @Test void outputCloseFailureRemainsTerminalAndDeletesSnapshot() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.OUTPUT_CLOSE);
        var admission = new ReadAdmission(2, 20000);
        assertSame(filesystem.closeFailure, assertThrows(UncheckedIOException.class,
                () -> decoded(filesystem, admission)).getCause());
        assertTrue(filesystem.outputWrites > 0);
        assertEquals(1, filesystem.deletionAttempts);
        settled(admission); assertEquals(0, files());
    }

    @Test void restorationReadFailureRemainsTerminalAndDeletesSnapshot() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.READ);
        var admission = new ReadAdmission(2, 20000);
        assertSame(filesystem.readFailure, assertThrows(UncheckedIOException.class,
                () -> decoded(filesystem, admission)).getCause());
        assertTrue(filesystem.outputWrites > 0);
        assertTrue(filesystem.restorationReads > 0);
        settled(admission); assertEquals(0, files());
    }

    @Test void deletionFailureRejectsResultButDoesNotInventSuccessfulFileCleanup() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.DELETE);
        var admission = new ReadAdmission(2, 20000);
        assertSame(filesystem.deleteFailure, assertThrows(UncheckedIOException.class,
                () -> decoded(filesystem, admission)).getCause());
        assertTrue(filesystem.restorationReads > 0);
        assertEquals(1, filesystem.deletionAttempts);
        settled(admission); assertEquals(1, files());
        // The operation reported failure. Explicit fixture cleanup is not a product recovery pass.
        cleanup();
    }

    @Test void deletionFailureIsSuppressedBehindTheOriginalWriteFailure() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.WRITE_AND_DELETE);
        var admission = new ReadAdmission(2, 20000);
        var failure = assertThrows(UncheckedIOException.class, () -> decoded(filesystem, admission));
        assertSame(filesystem.writeFailure, failure.getCause());
        assertTrue(java.util.Arrays.asList(failure.getCause().getSuppressed()).contains(filesystem.deleteFailure));
        settled(admission); assertEquals(1, files());
        cleanup();
    }

    private String decoded(SnapshotFaultFileSystem filesystem, ReadAdmission admission) {
        try {
            return SegmentedResourceText.read(new ByteArrayInputStream(TEXT.getBytes(StandardCharsets.UTF_8)),
                    StandardCharsets.UTF_8, admission, filesystem.wrap(directory));
        } catch (IOException failure) { throw new UncheckedIOException(failure); }
    }
    private void settled(ReadAdmission admission) {
        assertEquals(0, admission.active());
        assertEquals(0, admission.workspaceStatistics()[1]);
        assertEquals(0, admission.workspaceStatistics()[3]);
    }
    private long files() throws IOException {
        try (var files = Files.list(directory)) { return files.count(); }
    }
    private void cleanup() throws IOException {
        try (var files = Files.list(directory)) {
            for (Path path : files.toList()) Files.delete(path);
        }
        assertEquals(0, files());
    }
}
