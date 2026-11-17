package dev.abenli.neutralprobe;

import java.util.HashSet;
import java.util.Set;

/** Counts declarations separately from ID strings across all transport modes. */
public final class RegistrationCounts {
    private long declarations;
    private final Set<String> ids = new HashSet<>();
    public void add(String id) { declarations++; ids.add(id); }
    public long declarations() { return declarations; }
    public long distinctIds() { return ids.size(); }
}
