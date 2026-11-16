import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

/** JDK-only feasibility control; this does not replace or patch the packaged reader. */
public final class DeleteOnCloseControl {
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args[0]).toAbsolutePath();
        Path path = root.resolve("owned-channel-snapshot.utf16");
        byte[] expected = ("ab\u03b1\u4e2d\ud83d\ude86\u0000".repeat(5000)).getBytes(StandardCharsets.UTF_16BE);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try { Files.writeString(root.resolve("shutdown-hook-ran"), "normal shutdown"); }
            catch (Exception failure) { throw new RuntimeException(failure); }
        }));
        try (FileChannel channel = FileChannel.open(path, StandardOpenOption.CREATE_NEW,
                StandardOpenOption.READ, StandardOpenOption.WRITE, StandardOpenOption.DELETE_ON_CLOSE)) {
            ByteBuffer input = ByteBuffer.wrap(expected);
            while (input.hasRemaining()) channel.write(input);
            channel.force(false);
            channel.position(0);
            ByteBuffer restored = ByteBuffer.allocate(expected.length);
            while (restored.hasRemaining()) {
                if (channel.read(restored) < 0) throw new AssertionError("Unexpected snapshot EOF");
            }
            if (!Arrays.equals(expected, restored.array())) throw new AssertionError("Snapshot changed across rewind");
            String ready = "pid=" + ProcessHandle.current().pid() + "\nbytes=" + channel.size()
                    + "\nroundtrip=true\njava=" + System.getProperty("java.version") + "\n";
            Path temporary = root.resolve("ready.txt.tmp");
            Files.writeString(temporary, ready, StandardOpenOption.CREATE_NEW);
            Files.move(temporary, root.resolve("ready.txt"), StandardCopyOption.ATOMIC_MOVE);
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);
            while (!Files.exists(root.resolve("halt-after-observation"))) {
                if (System.nanoTime() > deadline) throw new AssertionError("Parent did not observe readiness");
                Thread.sleep(10);
            }
            Runtime.getRuntime().halt(75);
        }
        throw new AssertionError("Halt did not terminate the process");
    }
}
