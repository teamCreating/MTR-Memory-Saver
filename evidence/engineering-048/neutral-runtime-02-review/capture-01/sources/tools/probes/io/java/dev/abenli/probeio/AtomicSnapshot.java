package dev.abenli.probeio;

import com.sun.jna.Native;
import com.sun.jna.Platform;
import com.sun.jna.Pointer;
import com.sun.jna.WString;
import com.sun.jna.win32.StdCallLibrary;
import java.io.IOException;
import java.nio.file.FileSystemException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/** Single-publisher snapshots: concurrent readers retain one complete file version. */
public final class AtomicSnapshot {
    private AtomicSnapshot() {}

    public static void write(Path destination, String text) throws IOException {
        Path temporary = destination.resolveSibling(destination.getFileName() + ".tmp");
        Files.writeString(temporary, text);
        if (Platform.isWindows()) {
            // MoveFileExW(REPLACE_EXISTING), used by Files.move(ATOMIC_MOVE),
            // rejects an open target even when its readers grant delete sharing.
            // ReplaceFileW preserves those handles and publishes the new file.
            if (Windows.API.ReplaceFileW(new WString(destination.toAbsolutePath().toString()),
                    new WString(temporary.toAbsolutePath().toString()), null, 0, null, null) != 0) return;
            int error = Native.getLastError();
            // ReplaceFile requires an existing destination. Only first publication
            // uses rename; all other native failures remain visible to the caller.
            if (error != 2 || Files.exists(destination, LinkOption.NOFOLLOW_LINKS)) {
                throw new FileSystemException(temporary.toString(), destination.toString(),
                        "ReplaceFileW failed with Windows error " + error);
            }
        }
        Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE);
    }

    private interface WindowsApi extends StdCallLibrary {
        int ReplaceFileW(WString replaced, WString replacement, WString backup, int flags,
                         Pointer exclude, Pointer reserved);
    }

    private static final class Windows {
        private static final WindowsApi API = Native.load("kernel32", WindowsApi.class);
    }
}
