package site.benli06;

import java.util.concurrent.CancellationException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

/** Bounds active text/parse scopes, excluding native model and GPU RAM. */
public final class ReadAdmission {
    public static final ReadAdmission GLOBAL = new ReadAdmission(positiveProperty("mtr.memory.readers", 2),
            positiveLongProperty("mtr.memory.maxTextCodeUnits", Math.min(Integer.MAX_VALUE - 8L, Runtime.getRuntime().maxMemory() / 32)));
    private final Semaphore permits;
    private final long maxCodeUnits;
    private final ThreadLocal<Integer> depth = ThreadLocal.withInitial(() -> 0);
    private final AtomicInteger active = new AtomicInteger(), peak = new AtomicInteger();
    public ReadAdmission(int readers, long maxCodeUnits) {
        if (readers < 1 || maxCodeUnits < 1 || maxCodeUnits > Integer.MAX_VALUE - 8L)
            throw new IllegalArgumentException("Invalid resource read limits");
        permits = new Semaphore(readers, true);
        this.maxCodeUnits = maxCodeUnits;
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
        if (canceled.getAsBoolean()) throw new CancellationException("Resource read generation retired");
        if (depth.get() == 0) {
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
        depth.set(depth.get() + 1);
        return new Scope();
    }
    public void checkLength(long codeUnits) {
        if (Thread.currentThread().isInterrupted()) throw new CancellationException("Resource read interrupted");
        if (codeUnits > maxCodeUnits)
            throw new IllegalStateException("Resource text exceeds the configured limit of " + maxCodeUnits + " UTF-16 code units");
    }
    public long maxCodeUnits() { return maxCodeUnits; }
    public int active() { return active.get(); }
    public int peak() { return peak.get(); }
    public final class Scope implements AutoCloseable {
        private final Thread owner = Thread.currentThread();
        private boolean closed;
        private Scope() {}
        @Override public void close() {
            if (owner != Thread.currentThread()) throw new IllegalStateException("Read scope closed by another thread");
            if (closed) return;
            closed = true;
            int remaining = depth.get() - 1;
            if (remaining == 0) { depth.remove(); active.decrementAndGet(); permits.release(); }
            else depth.set(remaining);
        }
    }
}
