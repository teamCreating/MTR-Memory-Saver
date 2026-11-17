package site.benli06;

import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

@Timeout(20)
class GenerationWorkCacheTest {
    private final AtomicInteger tickets = new AtomicInteger();
    private final ReadAdmission admission = new ReadAdmission(2, 100_000);
    private GenerationWorkCache<String, String, String> cache(int workers, int queue, Duration timeout) {
        return new GenerationWorkCache<>(workers, queue, timeout, admission, tickets::incrementAndGet, tickets::decrementAndGet);
    }
    private GenerationWorkCache.Prepared<String, String> text(String value) { return new GenerationWorkCache.Prepared<>(value, () -> value); }
    @Test void pathHitSkipsPreparationAndContentAliasesParseOnce() throws Exception {
        var reads = new AtomicInteger(); var parses = new AtomicInteger();
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            var first = cache.get("path", () -> { reads.incrementAndGet(); return new GenerationWorkCache.Prepared<>("same", () -> { parses.incrementAndGet(); return "mesh"; }); });
            assertEquals("mesh", first.get());
            assertSame(first, cache.get("path", () -> fail("Path hit performed read/digest")));
            assertEquals("mesh", cache.get("alias", () -> { reads.incrementAndGet(); return new GenerationWorkCache.Prepared<>("same", () -> { parses.incrementAndGet(); return "duplicate"; }); }).get());
            assertEquals(2, reads.get()); assertEquals(1, parses.get());
            cache.finishRegistration(); assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
            clean(cache);
        }
    }
    @Test void providerIdentityAndTextureArePartOfFastKey() {
        Object first = new String("provider"), second = new String("provider");
        assertEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(first, "a", "b", false));
        assertNotEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(second, "a", "b", false));
        assertNotEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(first, "a", "c", false));
        assertNotEquals(new ResourceSourceKey(first, "a", "b", false), new ResourceSourceKey(first, "a", "b", true));
    }
    @Test void readAndParseFailureAllowRetryAndCleanTickets() throws Exception {
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            assertThrows(ExecutionException.class, () -> cache.get("path", () -> { throw new IllegalArgumentException("read"); }).get());
            assertThrows(ExecutionException.class, () -> cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> { throw new IllegalStateException("native parse ended without publication"); })).get());
            assertEquals("recovered", cache.get("path", () -> text("recovered")).get());
            assertEquals(2, cache.statistics().failures()); clean(cache);
        }
    }
    @Test void queueBackpressureDoesNotReadQueuedInputs() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var reads = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5)); var callers = Executors.newSingleThreadExecutor()) {
            var first = cache.get("a", () -> { reads.incrementAndGet(); entered.countDown(); await(release); return text("a"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var second = cache.get("b", () -> { reads.incrementAndGet(); return text("b"); });
            var third = callers.submit(() -> cache.get("c", () -> { reads.incrementAndGet(); return text("c"); }));
            assertThrows(TimeoutException.class, () -> third.get(80, TimeUnit.MILLISECONDS));
            assertEquals(1, reads.get()); assertEquals(2, cache.statistics().outstanding());
            release.countDown(); assertEquals("a", first.get()); assertEquals("b", second.get()); assertEquals("c", third.get().get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void reloadCancelsQueuedAndRunningWorkAndCannotPublishIntoNewEpoch() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var queuedReads = new AtomicInteger();
        try (var cache = cache(1, 2, Duration.ofSeconds(5))) {
            var old = cache.get("path", () -> {
                entered.countDown(); awaitIgnoringInterrupt(release); return text("old");
            });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var queued = cache.get("queued", () -> { queuedReads.incrementAndGet(); return text("queued"); });
            cache.beginReload(); assertTrue(old.isCancelled()); assertTrue(queued.isCancelled());
            assertEquals(1, tickets.get()); assertEquals(1, admission.active()); // Running memory still owns its permit.
            assertEquals(0, cache.statistics().pending());
            var fresh = cache.get("path", () -> text("new"));
            release.countDown(); assertEquals("new", fresh.get()); assertEquals(0, queuedReads.get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void timeoutIsTerminalButCannotReleaseStillRunningNativeMemory() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(1, 1, Duration.ofMillis(250))) {
            var hanging = cache.get("timeout", () -> { entered.countDown(); awaitIgnoringInterrupt(release); return text("late"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertInstanceOf(TimeoutException.class, assertThrows(ExecutionException.class, hanging::get).getCause());
            assertEquals(0, cache.statistics().pending()); assertEquals(1, tickets.get()); assertEquals(1, admission.active());
            release.countDown(); clean(cache);
            assertEquals("retry", cache.get("timeout", () -> text("retry")).get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void cancellationAndLateRegistrationCompletionReleaseEverything() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var running = cache.get("one", () -> { entered.countDown(); await(release); return text("one"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            assertTrue(running.cancel(true)); clean(cache);
            var later = cache.get("later", () -> text("later"));
            cache.finishRegistration(); assertEquals("later", later.get()); clean(cache);
            assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
        } finally { release.countDown(); }
    }
    @Test void oneThousandEpochsMixingSuccessFailureAndRetirementDoNotAccumulate() throws Exception {
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            for (int i = 0; i < 1000; i++) {
                assertEquals("mesh", cache.get("path", () -> text("mesh")).get());
                assertThrows(ExecutionException.class, () -> cache.get("bad", () -> { throw new IllegalStateException("fixture"); }).get());
                cache.finishRegistration(); cache.beginReload();
                assertEquals(0, cache.statistics().pending()); assertEquals(0, cache.statistics().paths());
            }
            clean(cache);
        }
    }
    @Test void admissionHookFailureReturnsSlot() throws Exception {
        var calls = new AtomicInteger();
        try (var cache = new GenerationWorkCache<String, String, String>(1, 1, Duration.ofSeconds(5), admission,
                () -> { if (calls.getAndIncrement() == 0) throw new IllegalStateException("construction hook"); tickets.incrementAndGet(); }, tickets::decrementAndGet)) {
            assertThrows(IllegalStateException.class, () -> cache.get("bad", () -> text("bad")));
            assertEquals("good", cache.get("good", () -> text("good")).get()); clean(cache);
        }
    }
    @Test void reloadRejectsCallerStillWaitingForDescriptorAdmission() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1); var staleReads = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            cache.get("running", () -> { entered.countDown(); awaitIgnoringInterrupt(release); return text("old"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            cache.get("queued", () -> text("queued"));
            var result = new CompletableFuture<CompletableFuture<String>>();
            Thread caller = new Thread(() -> {
                try { result.complete(cache.get("crossing", () -> { staleReads.incrementAndGet(); return text("stale"); })); }
                catch (Throwable error) { result.completeExceptionally(error); }
            });
            caller.start(); ThreadTestSupport.awaiting(caller, "acquireSlot");
            cache.beginReload();
            assertThrows(CancellationException.class, () -> result.get(5, TimeUnit.SECONDS));
            caller.join(); release.countDown(); clean(cache);
            assertEquals(0, staleReads.get()); assertEquals(0, cache.statistics().paths());
            assertEquals("fresh", cache.get("crossing", () -> text("fresh")).get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void failedContentOwnerTerminatesPendingAliasesAndBothPathsCanRetry() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var failure = new IllegalStateException("source failure");
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            var owner = cache.get("owner", () -> new GenerationWorkCache.Prepared<>("shared", () -> {
                entered.countDown(); await(release); throw failure;
            }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var alias = cache.get("alias", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Alias parsed")));
            eventually(() -> cache.statistics().pending() == 2 && cache.statistics().outstanding() == 1);
            release.countDown();
            assertSame(failure, assertThrows(ExecutionException.class, owner::get).getCause());
            assertSame(failure, assertThrows(ExecutionException.class, alias::get).getCause()); clean(cache);
            assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
            assertEquals("recovered", cache.get("owner", () -> new GenerationWorkCache.Prepared<>("shared", () -> "recovered")).get());
            assertEquals("recovered", cache.get("alias", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Retry alias parsed"))).get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void cancelingAliasPreservesOwnerAndSiblingAndLateRegistrationReleasesKeys() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            var owner = cache.get("owner", () -> new GenerationWorkCache.Prepared<>("shared", () -> {
                entered.countDown(); await(release); return "mesh";
            }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var alias = cache.get("alias", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Alias parsed")));
            var sibling = cache.get("sibling", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Sibling parsed")));
            eventually(() -> cache.statistics().pending() == 3 && cache.statistics().outstanding() == 1);
            assertTrue(alias.cancel(true)); assertFalse(owner.isDone()); assertFalse(sibling.isDone());
            cache.finishRegistration(); release.countDown();
            assertEquals("mesh", owner.get()); assertEquals("mesh", sibling.get()); clean(cache);
            assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
        } finally { release.countDown(); }
    }
    @Test void cancelingOwnerCancelsAliasesButRetainsRunningTicketUntilExit() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(2, 4, Duration.ofSeconds(5))) {
            var owner = cache.get("owner", () -> new GenerationWorkCache.Prepared<>("shared", () -> {
                entered.countDown(); awaitIgnoringInterrupt(release); return "late";
            }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var alias = cache.get("alias", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Alias parsed")));
            eventually(() -> cache.statistics().pending() == 2 && cache.statistics().outstanding() == 1);
            assertTrue(owner.cancel(true)); assertTrue(alias.isCancelled());
            assertEquals(0, cache.statistics().pending()); assertEquals(1, tickets.get()); assertEquals(1, admission.active());
            release.countDown(); clean(cache);
            assertEquals("retry", cache.get("alias", () -> text("retry")).get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void recursiveSaturatedAdmissionFailsInsteadOfBlockingWorker() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var owner = cache.get("owner", () -> {
                entered.countDown(); await(release);
                assertThrows(RejectedExecutionException.class, () -> cache.get("recursive", () -> text("unused")));
                return text("owner");
            });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var queued = cache.get("queued", () -> text("queued"));
            release.countDown(); assertEquals("owner", owner.get()); assertEquals("queued", queued.get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void interruptedDescriptorWaitPreservesInterruptAndCannotRead() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            cache.get("owner", () -> { entered.countDown(); await(release); return text("owner"); });
            assertTrue(entered.await(5, TimeUnit.SECONDS)); cache.get("queued", () -> text("queued"));
            var result = new CompletableFuture<Boolean>();
            Thread caller = new Thread(() -> {
                try {
                    assertThrows(CancellationException.class, () -> cache.get("interrupted", () -> fail("Interrupted caller read")));
                    result.complete(Thread.currentThread().isInterrupted());
                } catch (Throwable error) { result.completeExceptionally(error); }
            });
            caller.start(); ThreadTestSupport.awaiting(caller, "acquireSlot"); caller.interrupt();
            assertTrue(result.get(5, TimeUnit.SECONDS)); caller.join(); release.countDown(); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void preparedOwnerClosesExactlyOnceBeforeSuccessIsObservable() throws Exception {
        var closed = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> {
                assertEquals(0, closed.get()); return "mesh";
            }, closed::incrementAndGet));
            assertEquals("mesh", result.thenApply(value -> { assertEquals(1, closed.get()); return value; }).get());
            assertSame(result, cache.get("path", () -> fail("Path hit prepared another owner")));
            clean(cache); assertEquals(1, closed.get());
        }
    }
    @Test void parseFailureKeepsTheOwnerCloseFailureSuppressedBeforePublication() throws Exception {
        var failure = new IllegalStateException("parse failed");
        var closeFailure = new Exception("source close failed");
        var closed = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> { throw failure; }, () -> {
                closed.incrementAndGet(); throw closeFailure;
            }));
            assertSame(failure, assertThrows(ExecutionException.class, result::get).getCause());
            assertEquals(1, closed.get()); assertArrayEquals(new Throwable[] {closeFailure}, failure.getSuppressed());
            clean(cache); assertEquals(0, cache.statistics().contents());
        }
    }
    @Test void closeFailureCannotPublishAnOtherwiseSuccessfulValueAndAllowsRetry() throws Exception {
        var closeFailure = new Exception("source close failed");
        var closed = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> "unpublished", () -> {
                closed.incrementAndGet(); throw closeFailure;
            }));
            assertSame(closeFailure, assertThrows(ExecutionException.class, result::get).getCause());
            clean(cache); assertEquals(1, closed.get());
            assertEquals(0, cache.statistics().paths()); assertEquals(0, cache.statistics().contents());
            assertEquals("recovered", cache.get("path", () -> text("recovered")).get()); clean(cache);
        }
    }
    @Test void aliasReleasesItsPreparedWorkspaceBeforeWaitingForTheOwner() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var ownerClosed = new AtomicInteger(); var aliasClosed = new AtomicInteger();
        try (var cache = cache(2, 2, Duration.ofSeconds(5))) {
            var owner = cache.get("owner", () -> {
                var lease = admission.workspace().claim(2000);
                return new GenerationWorkCache.Prepared<>("shared", () -> {
                    entered.countDown(); await(release); return "mesh";
                }, () -> { lease.close(); ownerClosed.incrementAndGet(); });
            });
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var alias = cache.get("alias", () -> {
                var lease = admission.workspace().claim(1000);
                return new GenerationWorkCache.Prepared<>("shared", () -> fail("Alias parsed"),
                        () -> { lease.close(); aliasClosed.incrementAndGet(); });
            });
            eventually(() -> aliasClosed.get() == 1 && cache.statistics().outstanding() == 1);
            assertFalse(alias.isDone()); assertEquals(0, ownerClosed.get());
            assertEquals(2000, admission.workspaceStatistics()[1]);
            release.countDown(); assertEquals("mesh", owner.get()); assertEquals("mesh", alias.get());
            clean(cache); assertEquals(1, ownerClosed.get()); assertEquals(1, aliasClosed.get());
            assertEquals(0, admission.workspaceStatistics()[1]);
        } finally { release.countDown(); }
    }
    @Test void aliasCloseFailureCannotBorrowSuccessOrCancelTheContentOwner() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var closeFailure = new Exception("alias close failed"); var retryClosed = new AtomicInteger();
        try (var cache = cache(2, 2, Duration.ofSeconds(5))) {
            var owner = cache.get("owner", () -> new GenerationWorkCache.Prepared<>("shared", () -> {
                entered.countDown(); await(release); return "mesh";
            }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            var alias = cache.get("alias", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Alias parsed"),
                    () -> { throw closeFailure; }));
            assertSame(closeFailure, assertThrows(ExecutionException.class, alias::get).getCause());
            assertFalse(owner.isDone()); release.countDown(); assertEquals("mesh", owner.get()); clean(cache);
            var retry = cache.get("alias", () -> new GenerationWorkCache.Prepared<>("shared", () -> fail("Retry alias parsed"),
                    retryClosed::incrementAndGet));
            assertEquals("mesh", retry.thenApply(value -> { assertEquals(1, retryClosed.get()); return value; }).get());
            clean(cache);
        } finally { release.countDown(); }
    }
    @Test void retirementWhilePreparingClosesTheTransferredOwnerWithoutCallingLoad() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var closed = new AtomicInteger(); var loads = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var result = cache.get("old", () -> {
                entered.countDown(); awaitIgnoringInterrupt(release);
                return new GenerationWorkCache.Prepared<>("old", () -> { loads.incrementAndGet(); return "old"; }, closed::incrementAndGet);
            });
            assertTrue(entered.await(5, TimeUnit.SECONDS)); cache.beginReload();
            assertTrue(result.isCancelled()); assertEquals(0, closed.get());
            assertEquals(1, cache.statistics().outstanding()); assertEquals(1, admission.active());
            release.countDown(); clean(cache); assertEquals(1, closed.get()); assertEquals(0, loads.get());
            assertEquals("fresh", cache.get("old", () -> text("fresh")).get()); clean(cache);
        } finally { release.countDown(); }
    }
    @Test void cancellationAndTimeoutRetainRunningTicketsUntilOwnerCloseActuallyFinishes() throws Exception {
        for (boolean timeout : new boolean[] {false, true}) {
            var entered = new CountDownLatch(1); var releaseLoad = new CountDownLatch(1);
            var closing = new CountDownLatch(1); var releaseClose = new CountDownLatch(1); var closed = new AtomicInteger();
            try (var cache = cache(1, 1, timeout ? Duration.ofMillis(250) : Duration.ofSeconds(5))) {
                var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> {
                    entered.countDown(); awaitIgnoringInterrupt(releaseLoad); return "late";
                }, () -> { closing.countDown(); awaitIgnoringInterrupt(releaseClose); closed.incrementAndGet(); }));
                assertTrue(entered.await(5, TimeUnit.SECONDS));
                if (timeout) assertInstanceOf(TimeoutException.class, assertThrows(ExecutionException.class, result::get).getCause());
                else assertTrue(result.cancel(true));
                assertEquals(1, cache.statistics().outstanding()); assertEquals(1, admission.active());
                releaseLoad.countDown(); assertTrue(closing.await(5, TimeUnit.SECONDS));
                assertEquals(0, closed.get()); assertEquals(1, cache.statistics().outstanding());
                // Closing a source must not hold the generation lock or release its running ticket early.
                cache.finishRegistration();
                assertEquals(1, admission.active()); releaseClose.countDown(); clean(cache);
                assertEquals(1, closed.get()); assertTrue(result.isCompletedExceptionally());
            } finally { releaseLoad.countDown(); releaseClose.countDown(); }
        }
    }
    @Test void retirementFromOwnerCloseCannotPublishTheParsedValueIntoTheNewEpoch() throws Exception {
        var closed = new AtomicInteger();
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> "stale", () -> {
                cache.beginReload(); closed.incrementAndGet();
            }));
            assertThrows(CancellationException.class, result::get); clean(cache); assertEquals(1, closed.get());
            assertEquals("fresh", cache.get("path", () -> text("fresh")).get()); clean(cache);
        }
    }
    @Test void cancellationAndTimeoutPreserveLateOwnerCloseFailureOnTheOriginalTerminalCause() throws Exception {
        for (boolean timeout : new boolean[] {false, true}) {
            var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
            var closeFailure = new IOException("late source close failed");
            try (var cache = cache(1, 1, timeout ? Duration.ofMillis(250) : Duration.ofSeconds(5))) {
                var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> {
                    entered.countDown(); awaitIgnoringInterrupt(release); return "late";
                }, () -> { throw closeFailure; }));
                assertTrue(entered.await(5, TimeUnit.SECONDS));
                if (!timeout) assertTrue(result.cancel(true));
                Throwable primary = terminalFailure(result);
                if (timeout) assertInstanceOf(TimeoutException.class, primary);
                else assertInstanceOf(CancellationException.class, primary);
                assertEquals(1, cache.statistics().outstanding()); assertEquals(1, admission.active());
                release.countDown(); clean(cache);
                assertSame(primary, terminalFailure(result));
                assertArrayEquals(new Throwable[] {closeFailure}, primary.getSuppressed());
            } finally { release.countDown(); }
        }
    }
    @Test void retirementPreservesLateParseFailureAndItsSuppressedCloseFailure() throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var parseFailure = new IllegalStateException("late parse failed");
        var closeFailure = new IOException("late source close failed");
        try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
            var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> {
                entered.countDown(); awaitIgnoringInterrupt(release); throw parseFailure;
            }, () -> { throw closeFailure; }));
            assertTrue(entered.await(5, TimeUnit.SECONDS)); cache.beginReload();
            Throwable primary = terminalFailure(result); assertInstanceOf(CancellationException.class, primary);
            release.countDown(); clean(cache);
            assertSame(primary, terminalFailure(result));
            assertArrayEquals(new Throwable[] {parseFailure}, primary.getSuppressed());
            assertArrayEquals(new Throwable[] {closeFailure}, parseFailure.getSuppressed());
        } finally { release.countDown(); }
    }
    @Test void lateFailuresCannotAttachTheTerminalCauseBackOntoItselfOrDuplicateItsCleanupBranch() throws Exception {
        for (int mode = 0; mode < 3; mode++) {
            int selected = mode;
            var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
            var terminal = new AtomicReference<CancellationException>(); var thrown = new AtomicReference<Exception>();
            var closeFailure = new IOException("independent close failed");
            try (var cache = cache(1, 1, Duration.ofSeconds(5))) {
                var result = cache.get("path", () -> new GenerationWorkCache.Prepared<>("content", () -> {
                    entered.countDown(); awaitIgnoringInterrupt(release);
                    Exception error = selected == 0 ? new CompletionException(terminal.get())
                            : selected == 1 ? new IOException("wrapper") : terminal.get();
                    if (selected == 1) error.addSuppressed(terminal.get());
                    if (selected != 2) error.addSuppressed(closeFailure);
                    thrown.set(error); throw error;
                }, () -> { throw closeFailure; }));
                assertTrue(entered.await(5, TimeUnit.SECONDS)); assertTrue(result.cancel(true));
                var primary = assertInstanceOf(CancellationException.class, terminalFailure(result));
                terminal.set(primary); release.countDown(); clean(cache);
                assertSame(primary, terminalFailure(result));
                assertArrayEquals(new Throwable[] {closeFailure}, primary.getSuppressed());
                assertNull(closeFailure.getCause()); assertEquals(0, closeFailure.getSuppressed().length);
                if (selected == 2) assertSame(primary, thrown.get());
                else assertNotSame(primary, thrown.get());
            } finally { release.countDown(); }
        }
    }
    @Test void retiredEntryKeepsLateFailureBeforeCancellationAndBeforeInternalTerminalCallbackRuns() throws Exception {
        var entered = new CountDownLatch(2); var releaseLoads = new CountDownLatch(1);
        var cancelEntered = new CountDownLatch(1); var releaseCancel = new CountDownLatch(1);
        var firstCancellation = new AtomicBoolean(true); var closed = new AtomicInteger();
        var leftClose = new IOException("left close failed"); var rightClose = new IOException("right close failed");
        Thread retiring = null;
        try (var cache = cache(2, 2, Duration.ofSeconds(5))) {
            var left = cache.get("left", () -> new GenerationWorkCache.Prepared<>("left", () -> {
                entered.countDown(); awaitIgnoringInterrupt(releaseLoads); return "left";
            }, () -> { closed.incrementAndGet(); throw leftClose; }));
            var right = cache.get("right", () -> new GenerationWorkCache.Prepared<>("right", () -> {
                entered.countDown(); awaitIgnoringInterrupt(releaseLoads); return "right";
            }, () -> { closed.incrementAndGet(); throw rightClose; }));
            assertTrue(entered.await(5, TimeUnit.SECONDS));
            for (var result : java.util.List.of(left, right)) result.whenComplete((value, error) -> {
                if (firstCancellation.compareAndSet(true, false)) {
                    cancelEntered.countDown(); awaitIgnoringInterrupt(releaseCancel);
                }
            });
            var retired = new CompletableFuture<Void>();
            retiring = new Thread(() -> {
                try { cache.beginReload(); retired.complete(null); }
                catch (Throwable error) { retired.completeExceptionally(error); }
            });
            retiring.start(); assertTrue(cancelEntered.await(5, TimeUnit.SECONDS));
            assertNotEquals(left.isDone(), right.isDone());
            CompletableFuture<String> notYetCanceled = left.isDone() ? right : left;
            releaseLoads.countDown();
            eventually(() -> closed.get() == 2 && cache.statistics().outstanding() == 0 && admission.active() == 0);
            // One outcome is installed but its original internal terminal callback is
            // blocked behind the external callback; the other future is still pending.
            assertFalse(notYetCanceled.isDone());
            assertTrue(cache.statistics().pending() > 0);
            releaseCancel.countDown(); retired.get(5, TimeUnit.SECONDS); retiring.join();
            var leftPrimary = assertInstanceOf(CancellationException.class, terminalFailure(left));
            var rightPrimary = assertInstanceOf(CancellationException.class, terminalFailure(right));
            assertArrayEquals(new Throwable[] {leftClose}, leftPrimary.getSuppressed());
            assertArrayEquals(new Throwable[] {rightClose}, rightPrimary.getSuppressed()); clean(cache);
        } finally {
            releaseLoads.countDown(); releaseCancel.countDown();
            if (retiring != null) retiring.join(5000);
        }
    }
    private static Throwable terminalFailure(CompletableFuture<?> future) throws Exception {
        try { future.get(5, TimeUnit.SECONDS); fail("Work unexpectedly succeeded"); return null; }
        catch (CancellationException error) { return error; }
        catch (ExecutionException error) { return error.getCause(); }
    }
    private void clean(GenerationWorkCache<?, ?, ?> cache) throws Exception {
        eventually(() -> cache.statistics().outstanding() == 0 && tickets.get() == 0 && admission.active() == 0);
        assertEquals(0, cache.statistics().pending()); assertEquals(0, cache.statistics().queued());
    }
    private static void eventually(BooleanSupplier predicate) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!predicate.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(2);
        assertTrue(predicate.getAsBoolean(), "Cleanup did not complete");
    }
    private static void await(CountDownLatch latch) {
        try { if (!latch.await(5, TimeUnit.SECONDS)) throw new AssertionError("fixture timed out"); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new CancellationException(); }
    }
    private static void awaitIgnoringInterrupt(CountDownLatch latch) {
        while (true) { try { if (!latch.await(5, TimeUnit.SECONDS)) throw new AssertionError("fixture timed out"); return; } catch (InterruptedException ignored) {} }
    }
}
