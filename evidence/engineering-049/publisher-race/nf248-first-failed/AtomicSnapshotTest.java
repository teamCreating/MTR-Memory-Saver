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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
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

    @Test void posixReplacementKeepsARestrictiveDestinationReaderValid() throws Exception {
        assumeTrue(Platform.isWindows());
        Path destination = root.resolve("snapshot.json");
        AtomicSnapshot.write(destination, "original");
        WindowsApi api = Native.load("kernel32", WindowsApi.class);
        Pointer reader = api.CreateFileW(new WString(destination.toString()), 0x80000000, 3,
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
        AtomicSnapshot.write(destination, "retry");
        assertEquals("retry", Files.readString(destination));
    }

    @Test void deniedSourceDeleteHandleFailsWithoutMovingTheDestination() throws Exception {
        assumeTrue(Platform.isWindows());
        Path destination = root.resolve("snapshot.json");
        Path temporary = root.resolve("snapshot.json.tmp");
        AtomicSnapshot.write(destination, "original");
        Files.writeString(temporary, "source");
        WindowsApi api = Native.load("kernel32", WindowsApi.class);
        Pointer reader = api.CreateFileW(new WString(temporary.toString()), 0x80000000, 3, null, 3, 0x80, null);
        assertNotEquals(Pointer.createConstant(-1), reader);
        try {
            FileSystemException error = assertThrows(FileSystemException.class, () -> AtomicSnapshot.write(destination, "replacement"));
            assertTrue(error.getReason().contains("CreateFileW(DELETE) failed with Windows error"));
            assertEquals("original", Files.readString(destination));
            assertEquals("replacement", Files.readString(temporary));
        } finally {
            assertNotEquals(0, api.CloseHandle(reader));
        }
    }

    @Test void unicodeNameAndContentKeepTheirExactEncoding() throws Exception {
        Path destination = root.resolve("列车-🚆.json");
        AtomicSnapshot.write(destination, "车厢一\n");
        AtomicSnapshot.write(destination, "车厢二\n");
        assertEquals("车厢二\n", Files.readString(destination));
    }

    @Test void concurrentOpensAlwaysReadOneCompletePublishedVersion() throws Exception {
        assumeTrue(Platform.isWindows());
        Path destination = root.resolve("concurrent.json");
        AtomicSnapshot.write(destination, "epoch:0:complete\n");
        WindowsApi api = Native.load("kernel32", WindowsApi.class);
        var ready = new CountDownLatch(4);
        var start = new CountDownLatch(1);
        var stop = new AtomicBoolean();
        var successes = new AtomicLong();
        var failures = new ConcurrentLinkedQueue<String>();
        var readers = Executors.newFixedThreadPool(4);
        try {
            for (int index = 0; index < 4; index++) readers.submit(() -> {
                ready.countDown();
                try {
                    start.await();
                    while (!stop.get()) {
                        Pointer handle = api.CreateFileW(new WString(destination.toString()), 0x80000000, 7, null, 3, 0x80, null);
                        if (handle == null || handle.equals(Pointer.createConstant(-1))) {
                            failures.add("CreateFileW:" + Native.getLastError());
                            continue; // A separately counted next read, never a retry of this request.
                        }
                        try {
                            byte[] bytes = new byte[128];
                            IntByReference count = new IntByReference();
                            if (api.ReadFile(handle, bytes, bytes.length, count, null) == 0) failures.add("ReadFile:" + Native.getLastError());
                            else {
                                String value = new String(bytes, 0, count.getValue(), StandardCharsets.UTF_8);
                                if (!value.matches("epoch:[0-9]+:complete\\n")) failures.add("Incomplete payload:" + value);
                                else successes.incrementAndGet();
                            }
                        } finally {
                            if (api.CloseHandle(handle) == 0) failures.add("CloseHandle:" + Native.getLastError());
                        }
                    }
                } catch (Throwable error) {
                    failures.add(error.toString());
                }
            });
            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();
            for (int epoch = 1; epoch <= 1000; epoch++) AtomicSnapshot.write(destination, "epoch:" + epoch + ":complete\n");
        } finally {
            stop.set(true);
            start.countDown();
            readers.shutdown();
            assertTrue(readers.awaitTermination(10, TimeUnit.SECONDS));
        }
        System.out.println("FileRenameInfoEx: 1000 publications, " + successes.get() + " complete concurrent reads, " + failures.size() + " failures");
        assertTrue(successes.get() > 0);
        assertTrue(failures.isEmpty(), () -> failures.stream().limit(10).toList().toString());
        assertEquals("epoch:1000:complete\n", Files.readString(destination));
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
