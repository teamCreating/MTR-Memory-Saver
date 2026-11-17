package site.benli06;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/** Bounded descriptor queue, two-level single-flight lookup and atomic generation retirement. */
public final class GenerationWorkCache<K, C, V> implements AutoCloseable {
    public record Prepared<C, V>(C contentKey, Callable<V> load) {}
    public record Statistics(long requests, long pathHits, long uniqueParses, long failures,
                             int paths, int contents, int pending, int outstanding, int queued) {}
    private final class Epoch {
        final Map<K, Entry> paths = new HashMap<>();
        final Map<C, Entry> contents = new HashMap<>();
        final Set<Entry> pending = new HashSet<>();
        boolean retired, retain = true;
        long requests, hits, parses, failures;
    }
    private final class Entry {
        final K key;
        final Epoch epoch;
        final CompletableFuture<V> ready = new CompletableFuture<>();
        C content;
        boolean contentOwner;
        Work work;
        volatile ScheduledFuture<?> timer;
        Entry(K key, Epoch epoch) { this.key = key; this.epoch = epoch; }
    }
    private final class Work extends FutureTask<Void> {
        private boolean running, released;
        Work(Runnable action) { super(action, null); }
        @Override public void run() {
            synchronized (this) { if (isCancelled()) return; running = true; }
            try { super.run(); }
            finally { release(); }
        }
        @Override protected void done() {
            synchronized (this) { if (!running) release(); }
        }
        private synchronized void release() {
            if (released) return;
            released = true;
            try { exited.run(); }
            finally { outstanding.decrementAndGet(); slots.release(); }
        }
    }
    private final Object lock = new Object();
    private final Semaphore slots;
    private final AtomicInteger outstanding = new AtomicInteger();
    private final ThreadPoolExecutor workers;
    private final ScheduledThreadPoolExecutor timer;
    private final ThreadLocal<Boolean> inWorker = ThreadLocal.withInitial(() -> false);
    private final ReadAdmission admission;
    private final Runnable entered, exited;
    private final long timeoutMillis;
    private Epoch current = new Epoch();
    private volatile boolean closed;

    public GenerationWorkCache(int workerCount, int queueCapacity, Duration timeout, ReadAdmission admission,
                               Runnable entered, Runnable exited) {
        if (workerCount < 1 || queueCapacity < 1 || timeout.isNegative() || timeout.isZero())
            throw new IllegalArgumentException("Invalid parse scheduler limits");
        int capacity = Math.addExact(workerCount, queueCapacity);
        this.timeoutMillis = Math.max(1, timeout.toMillis());
        this.admission = admission; this.entered = entered; this.exited = exited;
        slots = new Semaphore(capacity, true);
        // The semaphore caps all submitted work, including tasks just leaving a worker.
        workers = new ThreadPoolExecutor(workerCount, workerCount, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(capacity), action -> daemon(action, "MTR-memory-parse"));
        timer = new ScheduledThreadPoolExecutor(1, action -> daemon(action, "MTR-memory-timeout"));
        timer.setRemoveOnCancelPolicy(true);
    }
    private static Thread daemon(Runnable action, String name) { Thread thread = new Thread(action, name); thread.setDaemon(true); return thread; }

    /** Preparation runs only on an admitted worker. Queued suppliers must capture descriptors, not text. */
    public CompletableFuture<V> get(K key, Supplier<Prepared<C, V>> prepare) {
        Epoch epoch;
        synchronized (lock) {
            requireOpen(); epoch = current; epoch.requests++;
            Entry existing = epoch.paths.get(key);
            if (existing != null) { epoch.hits++; return existing.ready; }
        }
        acquireSlot(epoch);
        Entry entry;
        synchronized (lock) {
            try { requireActive(epoch); }
            catch (RuntimeException error) { slots.release(); throw error; }
            Entry existing = epoch.paths.get(key);
            if (existing != null) { slots.release(); epoch.hits++; return existing.ready; }
            try { entered.run(); }
            catch (Throwable error) { slots.release(); throw error; }
            outstanding.incrementAndGet();
            entry = new Entry(key, epoch);
            entry.work = new Work(() -> execute(entry, prepare));
            epoch.paths.put(key, entry); epoch.pending.add(entry);
            entry.ready.whenComplete((value, error) -> terminal(entry, error));
        }
        try {
            entry.timer = timer.schedule(() -> entry.ready.completeExceptionally(
                    new TimeoutException("Shared model work exceeded " + timeoutMillis + " ms")), timeoutMillis, TimeUnit.MILLISECONDS);
            if (entry.ready.isDone()) entry.timer.cancel(false);
            workers.execute(entry.work);
            // Cancellation may race submission after its first removal attempt.
            if (entry.ready.isDone()) workers.remove(entry.work);
        } catch (RuntimeException error) { entry.ready.completeExceptionally(error); }
        return entry.ready;
    }
    private void acquireSlot(Epoch epoch) {
        synchronized (lock) { requireActive(epoch); }
        if (inWorker.get()) {
            if (!slots.tryAcquire()) throw new RejectedExecutionException("Recursive parse admission would block a worker");
            return;
        }
        long started = System.nanoTime();
        try {
            do {
                synchronized (lock) { requireActive(epoch); }
                if (slots.tryAcquire(Math.min(100, timeoutMillis), TimeUnit.MILLISECONDS)) return;
            } while (System.nanoTime() - started < TimeUnit.MILLISECONDS.toNanos(timeoutMillis));
            throw new RejectedExecutionException("Shared model queue admission timed out");
        } catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new CancellationException("Parse queue wait interrupted"); }
    }
    private void execute(Entry entry, Supplier<Prepared<C, V>> prepare) {
        inWorker.set(true);
        try (var scope = admission.open()) {
            if (entry.ready.isDone()) return;
            Prepared<C, V> prepared = prepare.get();
            CompletableFuture<V> alias;
            synchronized (lock) {
                if (entry.epoch.retired || entry.ready.isDone()) return;
                entry.content = prepared.contentKey();
                Entry existing = entry.epoch.contents.get(entry.content);
                alias = existing == null ? null : existing.ready;
                if (alias == null) {
                    entry.contentOwner = true;
                    entry.epoch.contents.put(entry.content, entry); entry.epoch.parses++;
                }
            }
            if (alias != null) {
                alias.whenComplete((value, error) -> publish(entry, value, error));
                return; // Never wait for another parser while holding a read scope/worker.
            }
            V value = prepared.load().call();
            if (value == null) throw new IllegalStateException("Shared model parser returned no result");
            publish(entry, value, null);
        } catch (Throwable error) { publish(entry, null, error); }
        finally { inWorker.remove(); }
    }
    private void publish(Entry entry, V value, Throwable error) {
        synchronized (lock) {
            if (entry.epoch.retired || entry.ready.isDone()) return;
            if (error == null) entry.ready.complete(value);
            else entry.ready.completeExceptionally(error);
        }
    }
    private void terminal(Entry entry, Throwable error) {
        synchronized (lock) {
            Epoch epoch = entry.epoch;
            epoch.pending.remove(entry);
            if (error != null || !epoch.retain) {
                epoch.paths.remove(entry.key, entry);
                if (entry.contentOwner) epoch.contents.remove(entry.content, entry);
            }
            if (error != null) epoch.failures++;
        }
        if (entry.timer != null) entry.timer.cancel(false);
        if (error != null) {
            entry.work.cancel(true);
            workers.remove(entry.work);
        }
    }
    public void beginReload() {
        ArrayList<Entry> pending;
        synchronized (lock) {
            Epoch old = current; old.retired = true;
            current = new Epoch();
            pending = new ArrayList<>(old.pending);
            old.paths.clear(); old.contents.clear();
        }
        pending.forEach(entry -> entry.ready.cancel(true));
    }
    /** Stops retaining successful sources; in-flight descriptors remain observable until terminal. */
    public void finishRegistration() {
        synchronized (lock) {
            current.retain = false;
            current.paths.values().removeIf(entry -> entry.ready.isDone());
            current.contents.values().removeIf(entry -> entry.ready.isDone());
        }
    }
    public Statistics statistics() {
        synchronized (lock) {
            return new Statistics(current.requests, current.hits, current.parses, current.failures,
                    current.paths.size(), current.contents.size(), current.pending.size(), outstanding.get(), workers.getQueue().size());
        }
    }
    private void requireOpen() { if (closed) throw new IllegalStateException("Parse scheduler closed"); }
    private void requireActive(Epoch epoch) {
        requireOpen();
        if (epoch.retired || epoch != current) throw new CancellationException("Parse admission generation retired");
    }
    @Override public void close() {
        closed = true; beginReload(); workers.shutdownNow(); timer.shutdownNow();
    }
}
