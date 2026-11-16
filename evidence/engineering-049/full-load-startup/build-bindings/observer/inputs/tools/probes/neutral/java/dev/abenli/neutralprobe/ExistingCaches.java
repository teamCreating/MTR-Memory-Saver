package dev.abenli.neutralprobe;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Copies existing native keys; it never asks native code to create a cache. */
public final class ExistingCaches {
    public record Entry<T>(int carKey, int totalCarsKey, T value) {}
    private ExistingCaches() {}

    public static <T> List<Entry<T>> entries(Map<Integer, ? extends Map<Integer, T>> caches) {
        var result = new ArrayList<Entry<T>>();
        for (var outer : caches.entrySet()) {
            for (var inner : outer.getValue().entrySet()) {
                if (inner.getValue() != null) result.add(new Entry<>(outer.getKey(), inner.getKey(), inner.getValue()));
            }
        }
        return result;
    }
}
