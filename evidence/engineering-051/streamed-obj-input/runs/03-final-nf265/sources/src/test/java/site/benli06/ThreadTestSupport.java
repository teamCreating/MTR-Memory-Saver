package site.benli06;

import static org.junit.jupiter.api.Assertions.assertTrue;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

final class ThreadTestSupport {
    private ThreadTestSupport() {}
    static void awaiting(Thread thread, String method) throws Exception {
        long started = System.nanoTime();
        while (System.nanoTime() - started < TimeUnit.SECONDS.toNanos(5)) {
            boolean inside = Arrays.stream(thread.getStackTrace()).anyMatch(frame -> frame.getMethodName().equals(method));
            Thread.State state = thread.getState();
            if (inside && (state == Thread.State.WAITING || state == Thread.State.TIMED_WAITING)) return;
            Thread.sleep(2);
        }
        assertTrue(false, "Caller never reached " + method + " wait");
    }
}
