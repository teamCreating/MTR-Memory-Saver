package dev.abenli.probeio;

import com.sun.jna.Native;
import com.sun.jna.Platform;
import com.sun.jna.Pointer;
import com.sun.jna.WString;
import com.sun.jna.ptr.IntByReference;
import com.sun.jna.win32.StdCallLibrary;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

final class AtomicSnapshotTest {
    @TempDir Path root;

    @Test void firstPublicationAndReplacementPreserveExactText() throws Exception {
        Path destination = root.resolve("snapshot.json");
        AtomicSnapshot.write(destination, "{\"epoch\":1,\"text\":\"列车\"}\n");
        assertEquals("{\"epoch\":1,\"text\":\"列车\"}\n", Files.readString(destination));
        AtomicSnapshot.write(destination, "{\"epoch\":2}\n");
        assertEquals("{\"epoch\":2}\n", Files.readString(destination));
        assertFalse(Files.exists(root.resolve("snapshot.json.tmp")));
    }

    @Test void deleteSharingReaderKeepsOldFileAcrossActualNativeReplacement() throws Exception {
        assumeTrue(Platform.isWindows());
        Path destination = root.resolve("snapshot.json");
        AtomicSnapshot.write(destination, "original");
        WindowsApi api = Native.load("kernel32", WindowsApi.class);
        Pointer reader = api.CreateFileW(new WString(destination.toString()), 0x80000000, 7,
                null, 3, 0x80, null);
        assertNotEquals(Pointer.createConstant(-1), reader);
        try {
            AtomicSnapshot.write(destination, "replacement");
            assertEquals("replacement", Files.readString(destination));
            byte[] bytes = new byte[64];
            IntByReference read = new IntByReference();
            assertNotEquals(0, api.ReadFile(reader, bytes, bytes.length, read, null));
            assertEquals("original", new String(bytes, 0, read.getValue(), StandardCharsets.UTF_8));
        } finally {
            assertNotEquals(0, api.CloseHandle(reader));
        }
    }

    @Test void restrictiveReaderPreservesNativeFailureAndAllowsLaterRetry() throws Exception {
        assumeTrue(Platform.isWindows());
        Path destination = root.resolve("snapshot.json");
        AtomicSnapshot.write(destination, "original");
        WindowsApi api = Native.load("kernel32", WindowsApi.class);
        Pointer reader = api.CreateFileW(new WString(destination.toString()), 0x80000000, 3,
                null, 3, 0x80, null);
        assertNotEquals(Pointer.createConstant(-1), reader);
        try {
            FileSystemException failure = assertThrows(FileSystemException.class,
                    () -> AtomicSnapshot.write(destination, "replacement"));
            assertTrue(failure.getReason().contains("ReplaceFileW failed with Windows error"));
            assertEquals("original", Files.readString(destination));
        } finally {
            assertNotEquals(0, api.CloseHandle(reader));
        }
        AtomicSnapshot.write(destination, "retry");
        assertEquals("retry", Files.readString(destination));
    }

    @Test void inaccessibleDestinationCannotBeReportedAsPublished() throws Exception {
        Path destination = root.resolve("absent/snapshot.json");
        assertThrows(java.io.IOException.class, () -> AtomicSnapshot.write(destination, "value"));
        assertFalse(Files.exists(destination));
    }

    private interface WindowsApi extends StdCallLibrary {
        Pointer CreateFileW(WString name, int access, int share, Pointer security,
                            int disposition, int flags, Pointer template);
        int ReadFile(Pointer file, byte[] bytes, int count, IntByReference read, Pointer overlapped);
        int CloseHandle(Pointer handle);
    }
}
