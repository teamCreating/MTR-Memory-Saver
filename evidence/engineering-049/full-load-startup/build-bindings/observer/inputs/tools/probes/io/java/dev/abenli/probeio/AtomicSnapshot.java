package dev.abenli.probeio;

import com.sun.jna.Native;
import com.sun.jna.Memory;
import com.sun.jna.Platform;
import com.sun.jna.Pointer;
import com.sun.jna.WString;
import com.sun.jna.win32.StdCallLibrary;
import java.io.IOException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.charset.StandardCharsets;

/** Single-publisher snapshots: concurrent readers retain one complete file version. */
public final class AtomicSnapshot {
    private AtomicSnapshot() {}

    public static void write(Path destination, String text) throws IOException {
        Path temporary = destination.resolveSibling(destination.getFileName() + ".tmp");
        Files.writeString(temporary, text);
        if (Platform.isWindows()) {
            publishWindows(temporary, destination);
            return;
        }
        Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE);
    }

    private static void publishWindows(Path temporary, Path destination) throws IOException {
        // Windows 10 1607+ FileRenameInfoEx performs one namespace rename. Its
        // POSIX flag keeps old handles valid and directs new opens to the new
        // file. ReplaceFileW exposes missing/sharing windows to concurrent opens.
        Pointer handle = Windows.API.CreateFileW(new WString(temporary.toAbsolutePath().toString()),
                0x00010000, 7, null, 3, 0x80, null); // DELETE, share read/write/delete, OPEN_EXISTING
        long invalidHandle = Native.POINTER_SIZE == 8 ? -1L : 0xffffffffL;
        if (handle == null || Pointer.nativeValue(handle) == invalidHandle) {
            throw failure(temporary, destination, "CreateFileW(DELETE)", Native.getLastError());
        }
        IOException prior = null;
        try {
            byte[] name = destination.toAbsolutePath().toString().getBytes(StandardCharsets.UTF_16LE);
            // FILE_RENAME_INFO: DWORD Flags, pointer-aligned HANDLE RootDirectory,
            // DWORD FileNameLength, WCHAR FileName[]. Length excludes the terminator.
            int rootOffset = Native.POINTER_SIZE;
            int lengthOffset = rootOffset + Native.POINTER_SIZE;
            int nameOffset = lengthOffset + 4;
            int size = Math.addExact(nameOffset, Math.addExact(name.length, 2));
            try (Memory information = new Memory(size)) {
                information.clear();
                information.setInt(0, 3); // FILE_RENAME_FLAG_REPLACE_IF_EXISTS | FILE_RENAME_FLAG_POSIX_SEMANTICS
                information.setPointer(rootOffset, null);
                information.setInt(lengthOffset, name.length);
                information.write(nameOffset, name, 0, name.length);
                if (Windows.API.SetFileInformationByHandle(handle, 22, information, size) == 0) {
                    throw failure(temporary, destination, "SetFileInformationByHandle(FileRenameInfoEx)", Native.getLastError());
                }
            }
        } catch (IOException error) {
            prior = error;
            throw error;
        } finally {
            if (Windows.API.CloseHandle(handle) == 0) {
                IOException error = failure(temporary, destination, "CloseHandle", Native.getLastError());
                if (prior != null) prior.addSuppressed(error);
                else throw error;
            }
        }
    }

    private static FileSystemException failure(Path source, Path destination, String operation, int error) {
        return new FileSystemException(source.toString(), destination.toString(),
                operation + " failed with Windows error " + error);
    }

    private interface WindowsApi extends StdCallLibrary {
        Pointer CreateFileW(WString name, int access, int share, Pointer security,
                            int disposition, int flags, Pointer template);
        int SetFileInformationByHandle(Pointer file, int informationClass, Pointer information, int size);
        int CloseHandle(Pointer handle);
    }

    private static final class Windows {
        private static final WindowsApi API = Native.load("kernel32", WindowsApi.class);
    }
}
