package site.benli06;

import java.io.IOException;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.nio.file.spi.FileSystemProvider;
import java.util.*;

/** Test-only forwarding filesystem: faults the real snapshot I/O, not the resource input. */
final class SnapshotFaultFileSystem extends FileSystem {
    enum Fault { NONE, CREATE, WRITE, CLOSE, READ, REWIND, WRITE_AND_CLOSE, SHORT_IO, ZERO_IO, ZERO_READ, ZERO_WRITE, COLLISION, UNSUPPORTED, TRUNCATE_ON_REWIND }
    final IOException createFailure = new IOException("snapshot channel creation failed");
    final IOException writeFailure = new IOException("snapshot output write failed");
    final IOException closeFailure = new IOException("snapshot owner close failed");
    final IOException readFailure = new IOException("snapshot restoration read failed");
    final IOException rewindFailure = new IOException("snapshot rewind failed");
    final UnsupportedOperationException unsupportedFailure = new UnsupportedOperationException("delete-on-close unsupported");
    private final FileSystem delegate = FileSystems.getDefault();
    private final Provider provider = new Provider();
    Fault fault;
    int createAttempts, outputWrites, restorationReads, closeCalls, zeroWrites, zeroReads;
    Set<? extends OpenOption> openedOptions;
    Path collisionPath;
    Runnable onZeroProgress = () -> {};
    SnapshotFaultFileSystem(Fault fault) { this.fault = fault; }
    Path wrap(Path path) { return new Wrapped(path); }
    Path unwrap(Path path) {
        if (path instanceof Wrapped wrapped && wrapped.getFileSystem() == this) return wrapped.path;
        throw new ProviderMismatchException();
    }
    @Override public FileSystemProvider provider() { return provider; }
    @Override public void close() { }
    @Override public boolean isOpen() { return true; }
    @Override public boolean isReadOnly() { return false; }
    @Override public String getSeparator() { return delegate.getSeparator(); }
    @Override public Iterable<Path> getRootDirectories() { throw new UnsupportedOperationException(); }
    @Override public Iterable<FileStore> getFileStores() { return delegate.getFileStores(); }
    @Override public Set<String> supportedFileAttributeViews() { return delegate.supportedFileAttributeViews(); }
    @Override public Path getPath(String first, String... more) { return wrap(delegate.getPath(first, more)); }
    @Override public PathMatcher getPathMatcher(String pattern) { return path -> delegate.getPathMatcher(pattern).matches(unwrap(path)); }
    @Override public UserPrincipalLookupService getUserPrincipalLookupService() { return delegate.getUserPrincipalLookupService(); }
    @Override public WatchService newWatchService() throws IOException { return delegate.newWatchService(); }

    private final class Provider extends FileSystemProvider {
        private final FileSystemProvider nativeProvider = delegate.provider();
        @Override public String getScheme() { return "snapshot-test"; }
        @Override public FileSystem newFileSystem(URI uri, Map<String, ?> env) { throw new UnsupportedOperationException(); }
        @Override public FileSystem getFileSystem(URI uri) { throw new UnsupportedOperationException(); }
        @Override public Path getPath(URI uri) { throw new UnsupportedOperationException(); }
        @Override public SeekableByteChannel newByteChannel(Path path, Set<? extends OpenOption> options,
                FileAttribute<?>... attrs) throws IOException {
            createAttempts++;
            if (fault == Fault.CREATE) throw createFailure;
            if (fault == Fault.UNSUPPORTED) throw unsupportedFailure;
            if (fault == Fault.COLLISION && createAttempts == 1) {
                collisionPath = unwrap(path);
                Files.writeString(collisionPath, "another owner's existing file", StandardOpenOption.CREATE_NEW);
                throw new FileAlreadyExistsException(path.toString());
            }
            openedOptions = Set.copyOf(options);
            var channel = nativeProvider.newByteChannel(unwrap(path), options, attrs);
            boolean output = options.contains(StandardOpenOption.WRITE);
            boolean input = options.isEmpty() || options.contains(StandardOpenOption.READ);
            return new SeekableByteChannel() {
                @Override public int read(ByteBuffer destination) throws IOException {
                    if (input) {
                        restorationReads++;
                        if (fault == Fault.READ) throw readFailure;
                        if (fault == Fault.ZERO_READ) { zeroReads++; onZeroProgress.run(); return 0; }
                        if (fault == Fault.ZERO_IO && restorationReads == 1) { zeroReads++; return 0; }
                    }
                    int limit = destination.limit();
                    if (fault == Fault.SHORT_IO) destination.limit(destination.position() + Math.min(7, destination.remaining()));
                    try { return channel.read(destination); }
                    finally { destination.limit(limit); }
                }
                @Override public int write(ByteBuffer source) throws IOException {
                    if (output) {
                        outputWrites++;
                        if (outputWrites == 1 && (fault == Fault.WRITE || fault == Fault.WRITE_AND_CLOSE)) throw writeFailure;
                        if (fault == Fault.ZERO_WRITE) { zeroWrites++; onZeroProgress.run(); return 0; }
                        if (fault == Fault.ZERO_IO && outputWrites == 1) { zeroWrites++; return 0; }
                    }
                    int limit = source.limit();
                    if (fault == Fault.SHORT_IO) source.limit(source.position() + Math.min(7, source.remaining()));
                    try { return channel.write(source); }
                    finally { source.limit(limit); }
                }
                @Override public long position() throws IOException { return channel.position(); }
                @Override public SeekableByteChannel position(long value) throws IOException {
                    if (fault == Fault.REWIND) throw rewindFailure;
                    if (fault == Fault.TRUNCATE_ON_REWIND) channel.truncate(channel.size() - 1);
                    channel.position(value); return this;
                }
                @Override public long size() throws IOException { return channel.size(); }
                @Override public SeekableByteChannel truncate(long size) throws IOException { channel.truncate(size); return this; }
                @Override public boolean isOpen() { return channel.isOpen(); }
                @Override public void close() throws IOException {
                    closeCalls++;
                    channel.close();
                    if (fault == Fault.CLOSE || fault == Fault.WRITE_AND_CLOSE) throw closeFailure;
                }
            };
        }
        @Override public DirectoryStream<Path> newDirectoryStream(Path directory, DirectoryStream.Filter<? super Path> filter)
                throws IOException {
            var stream = nativeProvider.newDirectoryStream(unwrap(directory), path -> filter.accept(wrap(path)));
            return new DirectoryStream<>() {
                @Override public Iterator<Path> iterator() {
                    var iterator = stream.iterator();
                    return new Iterator<>() {
                        @Override public boolean hasNext() { return iterator.hasNext(); }
                        @Override public Path next() { return wrap(iterator.next()); }
                    };
                }
                @Override public void close() throws IOException { stream.close(); }
            };
        }
        @Override public void createDirectory(Path path, FileAttribute<?>... attributes) throws IOException { nativeProvider.createDirectory(unwrap(path), attributes); }
        @Override public void delete(Path path) throws IOException {
            nativeProvider.delete(unwrap(path));
        }
        @Override public void copy(Path source, Path target, CopyOption... options) throws IOException { nativeProvider.copy(unwrap(source), unwrap(target), options); }
        @Override public void move(Path source, Path target, CopyOption... options) throws IOException { nativeProvider.move(unwrap(source), unwrap(target), options); }
        @Override public boolean isSameFile(Path first, Path second) throws IOException { return nativeProvider.isSameFile(unwrap(first), unwrap(second)); }
        @Override public boolean isHidden(Path path) throws IOException { return nativeProvider.isHidden(unwrap(path)); }
        @Override public FileStore getFileStore(Path path) throws IOException { return nativeProvider.getFileStore(unwrap(path)); }
        @Override public void checkAccess(Path path, AccessMode... modes) throws IOException { nativeProvider.checkAccess(unwrap(path), modes); }
        @Override public <V extends FileAttributeView> V getFileAttributeView(Path path, Class<V> type, LinkOption... options) {
            return nativeProvider.getFileAttributeView(unwrap(path), type, options);
        }
        @Override public <A extends BasicFileAttributes> A readAttributes(Path path, Class<A> type, LinkOption... options) throws IOException {
            return nativeProvider.readAttributes(unwrap(path), type, options);
        }
        @Override public Map<String, Object> readAttributes(Path path, String attributes, LinkOption... options) throws IOException {
            return nativeProvider.readAttributes(unwrap(path), attributes, options);
        }
        @Override public void setAttribute(Path path, String name, Object value, LinkOption... options) throws IOException {
            nativeProvider.setAttribute(unwrap(path), name, value, options);
        }
    }

    private final class Wrapped implements Path {
        private final Path path;
        Wrapped(Path path) { this.path = path; }
        @Override public FileSystem getFileSystem() { return SnapshotFaultFileSystem.this; }
        @Override public boolean isAbsolute() { return path.isAbsolute(); }
        @Override public Path getRoot() { return path.getRoot() == null ? null : wrap(path.getRoot()); }
        @Override public Path getFileName() { return path.getFileName() == null ? null : wrap(path.getFileName()); }
        @Override public Path getParent() { return path.getParent() == null ? null : wrap(path.getParent()); }
        @Override public int getNameCount() { return path.getNameCount(); }
        @Override public Path getName(int index) { return wrap(path.getName(index)); }
        @Override public Path subpath(int begin, int end) { return wrap(path.subpath(begin, end)); }
        @Override public boolean startsWith(Path other) { return path.startsWith(unwrap(other)); }
        @Override public boolean startsWith(String other) { return path.startsWith(other); }
        @Override public boolean endsWith(Path other) { return path.endsWith(unwrap(other)); }
        @Override public boolean endsWith(String other) { return path.endsWith(other); }
        @Override public Path normalize() { return wrap(path.normalize()); }
        @Override public Path resolve(Path other) { return wrap(path.resolve(unwrap(other))); }
        @Override public Path resolve(String other) { return wrap(path.resolve(other)); }
        @Override public Path resolveSibling(Path other) { return wrap(path.resolveSibling(unwrap(other))); }
        @Override public Path resolveSibling(String other) { return wrap(path.resolveSibling(other)); }
        @Override public Path relativize(Path other) { return wrap(path.relativize(unwrap(other))); }
        @Override public URI toUri() { throw new UnsupportedOperationException(); }
        @Override public Path toAbsolutePath() { return wrap(path.toAbsolutePath()); }
        @Override public Path toRealPath(LinkOption... options) throws IOException { return wrap(path.toRealPath(options)); }
        @Override public java.io.File toFile() { return path.toFile(); }
        @Override public WatchKey register(WatchService watcher, WatchEvent.Kind<?>[] events, WatchEvent.Modifier... modifiers) throws IOException {
            return path.register(watcher, events, modifiers);
        }
        @Override public Iterator<Path> iterator() {
            var iterator = path.iterator();
            return new Iterator<>() {
                @Override public boolean hasNext() { return iterator.hasNext(); }
                @Override public Path next() { return wrap(iterator.next()); }
            };
        }
        @Override public int compareTo(Path other) { return path.compareTo(unwrap(other)); }
        @Override public boolean equals(Object other) {
            return other instanceof Wrapped wrapped && wrapped.getFileSystem() == getFileSystem() && path.equals(wrapped.path);
        }
        @Override public int hashCode() { return path.hashCode(); }
        @Override public String toString() { return path.toString(); }
    }
}
