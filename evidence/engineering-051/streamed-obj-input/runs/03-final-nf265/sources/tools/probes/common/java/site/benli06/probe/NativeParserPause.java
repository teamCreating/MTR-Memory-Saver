package site.benli06.probe;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Fault injection belongs only to the separate observation JAR. */
public final class NativeParserPause {
    private static final AtomicReference<Gate> ACTIVE = new AtomicReference<>();
    private NativeParserPause() {}
    public static Gate arm() {
        var gate = new Gate();
        if (!ACTIVE.compareAndSet(null, gate)) throw new IllegalStateException("A native parser gate is already armed");
        return gate;
    }
    public static void beforeSubmit() {
        Gate gate = ACTIVE.get();
        if (gate == null || !gate.claimed.compareAndSet(false, true)) return;
        gate.entered.countDown();
        for (;;) try {
            gate.release.await();
            return;
        } catch (InterruptedException ignored) { gate.interrupted.set(true); }
    }
    public static final class Gate implements AutoCloseable {
        private final CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        private final AtomicBoolean claimed = new AtomicBoolean(), interrupted = new AtomicBoolean();
        public boolean awaitEntered() throws InterruptedException { return entered.await(5, TimeUnit.SECONDS); }
        public boolean interruptionObserved() { return interrupted.get(); }
        @Override public void close() { ACTIVE.compareAndSet(this, null); release.countDown(); }
    }
}
