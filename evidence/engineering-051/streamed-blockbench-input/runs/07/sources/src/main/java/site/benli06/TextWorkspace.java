package site.benli06;

import java.util.ArrayDeque;
import java.util.concurrent.CancellationException;

/** Atomic weighted admission for transient text payloads, excluding caller-retained results. */
final class TextWorkspace {
    private static final class Request {}
    private final long budget, share;
    private final Runnable checkCanceled;
    private final ArrayDeque<Request> waiting = new ArrayDeque<>();
    private final ThreadLocal<Lease> held = new ThreadLocal<>();
    private long used, peak;

    TextWorkspace(long budget, int readers, Runnable checkCanceled) {
        this.budget = budget;
        share = Math.max(4, budget / readers);
        this.checkCanceled = checkCanceled;
    }
    long share() { return share; }
    long budget() { return budget; }
    synchronized long[] statistics() { return new long[] {budget, used, peak, waiting.size()}; }

    Lease claim(long bytes) {
        if (bytes < 0 || bytes > budget) throw new IllegalArgumentException("Text workspace request exceeds its budget");
        // Never wait while retaining another payload reservation on this thread.
        if (held.get() != null) throw new IllegalStateException("Text workspace reservations cannot be nested");
        Request request = new Request();
        synchronized (this) {
            waiting.addLast(request);
            try {
                while (true) {
                    checkCanceled.run();
                    if (waiting.peekFirst() == request && bytes <= budget - used) {
                        waiting.removeFirst();
                        used += bytes; peak = Math.max(peak, used);
                        Lease lease = new Lease(bytes); held.set(lease);
                        notifyAll();
                        return lease;
                    }
                    wait(100);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new CancellationException("Text workspace wait interrupted");
            } finally {
                if (waiting.remove(request)) notifyAll();
            }
        }
    }
    synchronized Lease tryClaim(long bytes) {
        if (bytes < 0 || bytes > budget) throw new IllegalArgumentException("Text workspace request exceeds its budget");
        if (held.get() != null) throw new IllegalStateException("Text workspace reservations cannot be nested");
        checkCanceled.run();
        if (!waiting.isEmpty() || bytes > budget - used) return null;
        used += bytes; peak = Math.max(peak, used);
        Lease lease = new Lease(bytes); held.set(lease);
        return lease;
    }
    final class Lease implements AutoCloseable {
        private final Thread owner = Thread.currentThread();
        private long bytes;
        private boolean closed;
        private Lease(long bytes) { this.bytes = bytes; }
        @Override public void close() {
            if (owner != Thread.currentThread()) throw new IllegalStateException("Text workspace closed by another thread");
            synchronized (TextWorkspace.this) {
                if (closed) return;
                closed = true; used -= bytes; held.remove();
                TextWorkspace.this.notifyAll();
            }
        }
    }
}
