package dev.abenli.mtrmemory;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import dev.abenli.mtrmemory.mixin.DisplayPartAccess;
import org.mtr.model.ModelLoaderBase;
import org.mtr.resource.ModelProperties;
import org.mtr.resource.PartType;

/** The release consumes raw display transforms only for DISPLAY parts. */
public final class DisplayRetention {
    public interface Loader { void selectDisplays(Set<String> names); }
    private DisplayRetention() {}

    public static void configure(ModelLoaderBase loader, ModelProperties properties) {
        if (!(loader instanceof Loader selected)) return;
        Set<String> names = new HashSet<>();
        properties.iterateParts(part -> {
            DisplayPartAccess fields = (DisplayPartAccess) (Object) part;
            if (fields.partType() == PartType.DISPLAY) names.addAll(fields.partNames());
        });
        selected.selectDisplays(Set.copyOf(names));
    }

    public static <T> void retain(Map<String, T> displays, Set<String> names) {
        displays.keySet().removeIf(name -> !names.contains(name));
    }
}
