package dev.abenli.neutralprobe;

import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

/** Captured invalid invocations; failed nested calls cannot acquire another call's return. */
public final class DiagnosticTracker {
    public record Call(long id, Long epochId, int nesting, String model, String texture, boolean flip) {}
    public record State(long started, long completed, long inFlight) {}
    private final Map<Long, ArrayDeque<Call>> stacks = new HashMap<>();
    private long started, completed;

    public synchronized Call begin(long threadId, Long epochId, int nesting, String model, String texture, boolean flip) {
        if (nesting < 1) throw new IllegalArgumentException("Native factory depth must be positive");
        var stack = stacks.computeIfAbsent(threadId, ignored -> new ArrayDeque<>());
        while (!stack.isEmpty() && stack.peekLast().nesting() >= nesting) stack.removeLast();
        Call call = new Call(++started, epochId, nesting, model, texture, flip);
        stack.addLast(call);
        return call;
    }
    public synchronized Call end(long threadId, Long epochId, int nesting, String model, String texture, boolean flip) {
        var stack = stacks.get(threadId);
        if (stack == null) return null;
        while (!stack.isEmpty() && stack.peekLast().nesting() > nesting) stack.removeLast();
        if (stack.isEmpty()) { stacks.remove(threadId); return null; }
        Call call = stack.peekLast();
        if (call.nesting() != nesting || !Objects.equals(call.epochId(), epochId)
                || !Objects.equals(call.model(), model) || !Objects.equals(call.texture(), texture) || call.flip() != flip)
            return null;
        stack.removeLast();
        if (stack.isEmpty()) stacks.remove(threadId);
        completed++;
        return call;
    }
    public synchronized State state() { return new State(started, completed, started - completed); }
}
