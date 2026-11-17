package dev.abenli.neutralprobe;

import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;

/** Tracks observed invocations, including exceptional exits without a RETURN. */
public final class EpochTracker {
    public record Call(long sequence, int nesting) {}
    public record State(long started, long completed, long inFlight, int maxNesting, long lastCompletedSequence) {}
    private final Map<Long, ArrayDeque<Call>> stacks = new HashMap<>();
    private long started, completed, lastCompletedSequence;
    private int maxNesting;

    public synchronized Call begin(long threadId, int nesting) {
        if (nesting < 1) throw new IllegalArgumentException("Native stack depth must be positive");
        var stack = stacks.computeIfAbsent(threadId, ignored -> new ArrayDeque<>());
        // A later invocation at the same depth proves older unreturned frames
        // exited exceptionally. Keep their unmatched HEADs in the totals/log.
        while (!stack.isEmpty() && stack.peekLast().nesting() >= nesting) stack.removeLast();
        Call call = new Call(++started, nesting);
        stack.addLast(call);
        maxNesting = Math.max(maxNesting, nesting);
        return call;
    }

    public synchronized Call end(long threadId, int nesting) {
        var stack = stacks.get(threadId);
        if (stack == null) return null;
        // An inner failure may be caught by an outer reload. Never pair that
        // failed inner HEAD with the successful outer RETURN.
        while (!stack.isEmpty() && stack.peekLast().nesting() > nesting) stack.removeLast();
        Call call = !stack.isEmpty() && stack.peekLast().nesting() == nesting ? stack.removeLast() : null;
        if (stack.isEmpty()) stacks.remove(threadId);
        if (call != null) {
            completed++;
            lastCompletedSequence = call.sequence();
        }
        return call;
    }

    public synchronized State state() {
        return new State(started, completed, started - completed, maxNesting, lastCompletedSequence);
    }

    /** Return the actually active frame at this depth, never the last completed epoch. */
    public synchronized Call current(long threadId, int nesting) {
        var stack = stacks.get(threadId);
        if (stack == null || nesting < 1) return null;
        for (var call : stack) if (call.nesting() == nesting) return call;
        return null;
    }
}
