package dev.abenli.neutralprobe;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class EpochTrackerTest {
    @Test void nestedAndConcurrentThreadsPairTheirOwnInvocations() {
        var tracker = new EpochTracker();
        var outer = tracker.begin(1, 1);
        var inner = tracker.begin(1, 2);
        var concurrent = tracker.begin(2, 1);
        assertEquals(inner, tracker.end(1, 2));
        assertEquals(concurrent, tracker.end(2, 1));
        assertEquals(outer, tracker.end(1, 1));
        assertEquals(new EpochTracker.State(3, 3, 0, 2, outer.sequence()), tracker.state());
    }
    @Test void exceptionalReloadIsNeverCompletedByTheNextReload() {
        var tracker = new EpochTracker();
        var failed = tracker.begin(1, 1);
        var next = tracker.begin(1, 1);
        assertNotEquals(failed.sequence(), next.sequence());
        assertEquals(next, tracker.end(1, 1));
        assertEquals(new EpochTracker.State(2, 1, 1, 1, next.sequence()), tracker.state());
    }
    @Test void caughtInnerFailureDoesNotStealTheOuterReturn() {
        var tracker = new EpochTracker();
        var outer = tracker.begin(1, 1);
        tracker.begin(1, 2);
        assertEquals(outer, tracker.end(1, 1));
        assertEquals(1, tracker.state().inFlight());
        assertEquals(1, tracker.state().completed());
    }
    @Test void unmatchedReturnCannotFabricateCompletedWork() {
        var tracker = new EpochTracker();
        assertNull(tracker.end(9, 1));
        assertEquals(0, tracker.state().completed());
        assertThrows(IllegalArgumentException.class, () -> tracker.begin(9, 0));
    }
}
