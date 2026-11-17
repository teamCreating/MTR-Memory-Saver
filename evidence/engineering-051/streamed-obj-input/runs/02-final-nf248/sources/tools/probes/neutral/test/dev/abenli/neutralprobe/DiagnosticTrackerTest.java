package dev.abenli.neutralprobe;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class DiagnosticTrackerTest {
    @Test void nestedAndConcurrentInvalidCallsPairOnlyTheirOwnReturns() {
        var tracker = new DiagnosticTracker();
        var outer = tracker.begin(1, 10L, 1, "", "", false);
        var inner = tracker.begin(1, 10L, 2, "invalid", "texture", true);
        var concurrent = tracker.begin(2, 11L, 1, "", "", false);
        assertEquals(inner, tracker.end(1, 10L, 2, "invalid", "texture", true));
        assertEquals(concurrent, tracker.end(2, 11L, 1, "", "", false));
        assertEquals(outer, tracker.end(1, 10L, 1, "", "", false));
        assertEquals(new DiagnosticTracker.State(3, 3, 0), tracker.state());
    }
    @Test void failedInnerOrPriorCallCannotStealLaterReturn() {
        var tracker = new DiagnosticTracker();
        var outer = tracker.begin(1, 10L, 1, "", "", false);
        tracker.begin(1, 10L, 2, "invalid", "texture", true);
        assertEquals(outer, tracker.end(1, 10L, 1, "", "", false));
        tracker.begin(1, 11L, 1, "", "", false);
        var next = tracker.begin(1, 12L, 1, "", "", false);
        assertEquals(next, tracker.end(1, 12L, 1, "", "", false));
        assertEquals(new DiagnosticTracker.State(4, 2, 2), tracker.state());
    }
    @Test void changedEpochArgumentsDepthOrThreadNeverCompletesACall() {
        var tracker = new DiagnosticTracker();
        tracker.begin(1, 10L, 1, "", "", false);
        assertNull(tracker.end(1, 11L, 1, "", "", false));
        assertNull(tracker.end(1, 10L, 1, "different", "", false));
        assertNull(tracker.end(1, 10L, 1, "", "different", false));
        assertNull(tracker.end(1, 10L, 1, "", "", true));
        assertNull(tracker.end(1, 10L, 2, "", "", false));
        assertNull(tracker.end(2, 10L, 1, "", "", false));
        assertEquals(new DiagnosticTracker.State(1, 0, 1), tracker.state());
    }
    @Test void outsideEpochIsKeptExplicitInsteadOfAssigningLastEpoch() {
        var tracker = new DiagnosticTracker();
        var call = tracker.begin(1, null, 1, "", "", false);
        assertNull(call.epochId()); assertEquals(call, tracker.end(1, null, 1, "", "", false));
        var epochs = new EpochTracker();
        var epoch = epochs.begin(1, 1); var inner = epochs.begin(1, 2);
        assertEquals(epoch, epochs.current(1, 1)); assertEquals(inner, epochs.current(1, 2));
        assertNull(epochs.current(2, 1)); assertNull(epochs.current(1, 0));
        epochs.end(1, 1);
        assertNull(epochs.current(1, 1)); assertNull(epochs.current(1, 2));
    }
}
