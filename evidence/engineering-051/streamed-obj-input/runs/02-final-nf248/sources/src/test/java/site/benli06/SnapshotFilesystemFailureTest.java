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

    @Test void ownerCloseFailureRemainsTerminalAndDeletesSnapshot() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.CLOSE);
        var admission = new ReadAdmission(2, 20000);
        assertSame(filesystem.closeFailure, assertThrows(UncheckedIOException.class,
                () -> decoded(filesystem, admission)).getCause());
        assertTrue(filesystem.outputWrites > 0);
        assertTrue(filesystem.restorationReads > 0);
        assertEquals(1, filesystem.closeCalls);
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

    @Test void rewindFailureRejectsResultAndClosesItsOwner() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.REWIND);
        var admission = new ReadAdmission(2, 20000);
        assertSame(filesystem.rewindFailure, assertThrows(UncheckedIOException.class,
                () -> decoded(filesystem, admission)).getCause());
        assertEquals(0, filesystem.restorationReads);
        assertEquals(1, filesystem.closeCalls);
        settled(admission); assertEquals(0, files());
    }

    @Test void ownerCloseFailureIsSuppressedBehindTheOriginalWriteFailure() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.WRITE_AND_CLOSE);
        var admission = new ReadAdmission(2, 20000);
        var failure = assertThrows(UncheckedIOException.class, () -> decoded(filesystem, admission));
        assertSame(filesystem.writeFailure, failure.getCause());
        assertTrue(java.util.Arrays.asList(failure.getCause().getSuppressed()).contains(filesystem.closeFailure));
        assertEquals(1, filesystem.closeCalls);
        settled(admission); assertEquals(0, files());
    }

    @Test void creationFailureCannotPublishAnEmptyEntryAndSameKeyRetries() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.CREATE);
        var admission = new ReadAdmission(2, 20000);
        var cache = new BoundedTextCache(100000, admission);
        var failure = assertThrows(UncheckedIOException.class,
                () -> cache.get("source", ignored -> decoded(filesystem, admission)));
        assertSame(filesystem.createFailure, failure.getCause());
        assertEquals(0, filesystem.closeCalls);
        assertEquals(0, cache.statistics()[0]);
        settled(admission); assertEquals(0, files());
        filesystem.fault = SnapshotFaultFileSystem.Fault.NONE;
        assertEquals(TEXT, cache.get("source", ignored -> decoded(filesystem, admission)));
        assertEquals(TEXT, cache.get("source", ignored -> fail("Successful retry was not cached")));
        settled(admission); assertEquals(0, files());
    }

    @Test void oddPartialReadsAndWritesPreserveUtf16AcrossNativeChannelCalls() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.SHORT_IO);
        var admission = new ReadAdmission(2, 20000);
        assertEquals(TEXT, decoded(filesystem, admission));
        assertTrue(filesystem.outputWrites > 1000);
        assertTrue(filesystem.restorationReads > 1000);
        assertEquals(1, filesystem.closeCalls);
        assertEquals(java.util.Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.READ,
                StandardOpenOption.WRITE, StandardOpenOption.DELETE_ON_CLOSE), filesystem.openedOptions);
        settled(admission); assertEquals(0, files());
    }

    @Test void transientZeroProgressIsNeitherEofNorLostOutput() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.ZERO_IO);
        var admission = new ReadAdmission(2, 20000);
        assertEquals(TEXT, decoded(filesystem, admission));
        assertEquals(1, filesystem.zeroWrites);
        assertEquals(1, filesystem.zeroReads);
        settled(admission); assertEquals(0, files());
    }

    @Test void retirementCancelsPersistentZeroProgressAndReleasesTheOwner() throws Exception {
        for (var fault : new SnapshotFaultFileSystem.Fault[]{SnapshotFaultFileSystem.Fault.ZERO_READ, SnapshotFaultFileSystem.Fault.ZERO_WRITE}) {
            var filesystem = new SnapshotFaultFileSystem(fault);
            var admission = new ReadAdmission(2, 20000);
            var retired = new java.util.concurrent.atomic.AtomicBoolean();
            filesystem.onZeroProgress = () -> {
                if (filesystem.zeroReads + filesystem.zeroWrites == 3) retired.set(true);
            };
            try (var scope = admission.open(retired::get)) {
                assertThrows(java.util.concurrent.CancellationException.class, () -> decoded(filesystem, admission));
            }
            assertEquals(3, filesystem.zeroReads + filesystem.zeroWrites);
            assertEquals(1, filesystem.closeCalls);
            settled(admission); assertEquals(0, files());
        }
    }

    @Test void nameCollisionNeverOverwritesOrDeletesAnotherOwnersFile() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.COLLISION);
        var admission = new ReadAdmission(2, 20000);
        assertEquals(TEXT, decoded(filesystem, admission));
        assertEquals(2, filesystem.createAttempts);
        assertEquals("another owner's existing file", Files.readString(filesystem.collisionPath));
        assertEquals(1, filesystem.closeCalls);
        settled(admission); assertEquals(1, files());
    }

    @Test void unsupportedDeleteOwnershipNeverFallsBackToAnUnownedFile() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.UNSUPPORTED);
        var admission = new ReadAdmission(2, 20000);
        assertSame(filesystem.unsupportedFailure, assertThrows(UnsupportedOperationException.class,
                () -> decoded(filesystem, admission)));
        assertEquals(1, filesystem.createAttempts);
        assertEquals(0, filesystem.closeCalls);
        settled(admission); assertEquals(0, files());
    }

    @Test void actualOddTruncationIsRejectedBeforePublishingText() throws Exception {
        var filesystem = new SnapshotFaultFileSystem(SnapshotFaultFileSystem.Fault.TRUNCATE_ON_REWIND);
        var admission = new ReadAdmission(2, 20000);
        assertTrue(assertThrows(UncheckedIOException.class, () -> decoded(filesystem, admission))
                .getCause().getMessage().contains("decoded length mismatch"));
        assertEquals(1, filesystem.closeCalls);
        settled(admission); assertEquals(0, files());
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
}
