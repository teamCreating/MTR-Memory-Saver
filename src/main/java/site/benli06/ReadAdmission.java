package site.benli06;

import java.util.concurrent.CancellationException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

/** Bounds active text/parse scopes, excluding native model and GPU RAM. */
public final class ReadAdmission {
    public static final ReadAdmission GLOBAL = configured(Runtime.getRuntime().maxMemory());
    private final Semaphore permits;
    private final long maxCodeUnits;
    private final TextWorkspace workspace;
    private final ThreadLocal<Scope> currentScope = new ThreadLocal<>();
    private final AtomicInteger active = new AtomicInteger(), peak = new AtomicInteger();
    public ReadAdmission(int readers, long maxCodeUnits) {
        this(readers, maxCodeUnits, requiredWorkspace(maxCodeUnits));
    }
    public ReadAdmission(int readers, long maxCodeUnits, long workspaceBytes) {
        if (readers < 1 || maxCodeUnits < 1 || maxCodeUnits > Integer.MAX_VALUE - 8L)
            throw new IllegalArgumentException("Invalid resource read limits");
        if (workspaceBytes < 4L * maxCodeUnits)
            throw new IllegalArgumentException("Text workspace must fit the configured decoded text limit");
        permits = new Semaphore(readers, true);
        this.maxCodeUnits = maxCodeUnits;
        workspace = new TextWorkspace(workspaceBytes, readers, () -> checkLength(0));
    }
    static long defaultMaxCodeUnits(long heapBytes) {
        if (heapBytes < 16) throw new IllegalArgumentException("Heap is too small for text workspace");
        return Math.min(Integer.MAX_VALUE - 8L, heapBytes / 16);
    }
    static ReadAdmission configured(long heapBytes) {
        long limit = positiveLongProperty("mtr.memory.maxTextCodeUnits", defaultMaxCodeUnits(heapBytes));
        long budget = positiveLongProperty("mtr.memory.textWorkspaceBytes", Math.max(heapBytes / 4, requiredWorkspace(limit)));
        return new ReadAdmission(positiveProperty("mtr.memory.readers", 2), limit, budget);
    }
    private static long requiredWorkspace(long limit) {
        if (limit < 1 || limit > Integer.MAX_VALUE - 8L) throw new IllegalArgumentException("Invalid decoded text limit");
        return 4L * limit;
    }
    public static int positiveProperty(String name, int fallback) {
        long value = positiveLongProperty(name, fallback);
        if (value > Integer.MAX_VALUE) throw new IllegalArgumentException(name + " exceeds the integer range");
        return (int) value;
    }
    public static long positiveLongProperty(String name, long fallback) {
        String configured = System.getProperty(name);
        long value;
        try { value = configured == null ? fallback : Long.decode(configured); }
        catch (NumberFormatException error) { throw new IllegalArgumentException(name + " must be a positive integer", error); }
        if (value < 1) throw new IllegalArgumentException(name + " must be positive");
        return value;
    }
    public Scope open() {
        return open(() -> false);
    }
    public Scope open(BooleanSupplier canceled) {
        checkCanceled();
        if (canceled.getAsBoolean()) throw new CancellationException("Resource read generation retired");
        Scope parent = currentScope.get();
        if (parent == null) {
            boolean acquired = false;
            try {
                while (!(acquired = permits.tryAcquire(100, TimeUnit.MILLISECONDS))) {
                    if (canceled.getAsBoolean()) throw new CancellationException("Resource read generation retired");
                }
                if (canceled.getAsBoolean()) throw new CancellationException("Resource read generation retired");
            }
            catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new CancellationException("Interrupted while awaiting resource read admission");
            }
            catch (RuntimeException | Error error) {
                if (acquired) permits.release();
                throw error;
            }
            peak.accumulateAndGet(active.incrementAndGet(), Math::max);
        }
        Scope scope = new Scope(parent, canceled);
        currentScope.set(scope);
        return scope;
    }
    public void checkLength(long codeUnits) {
        checkCanceled();
        if (codeUnits < 0) throw new IllegalArgumentException("Resource text length must not be negative");
        if (codeUnits > maxCodeUnits)
            throw new IllegalStateException("Resource text exceeds the configured limit of " + maxCodeUnits + " UTF-16 code units");
    }
    private void checkCanceled() {
        if (Thread.currentThread().isInterrupted()) throw new CancellationException("Resource read interrupted");
        for (Scope scope = currentScope.get(); scope != null; scope = scope.parent)
            if (scope.canceled.getAsBoolean()) throw new CancellationException("Resource read generation retired");
    }
    TextWorkspace workspace() { return workspace; }
    public long[] workspaceStatistics() { return workspace.statistics(); }
    public long maxCodeUnits() { return maxCodeUnits; }
    public int active() { return active.get(); }
    public int peak() { return peak.get(); }
    public final class Scope implements AutoCloseable {
        private final Thread owner = Thread.currentThread();
        private final Scope parent;
        private final BooleanSupplier canceled;
        private boolean closed;
        private Scope(Scope parent, BooleanSupplier canceled) { this.parent = parent; this.canceled = canceled; }
        @Override public void close() {
            if (owner != Thread.currentThread()) throw new IllegalStateException("Read scope closed by another thread");
            if (closed) return;
            if (currentScope.get() != this) throw new IllegalStateException("Read scopes must close in reverse order");
            closed = true;
            if (parent == null) { currentScope.remove(); active.decrementAndGet(); permits.release(); }
            else currentScope.set(parent);
        }
    }
}
