package dev.abenli.neutralprobe;

import java.util.LinkedHashMap;
import java.util.Map;
import org.mtr.client.CustomResourceLoader;
import org.mtr.core.data.TransportMode;
import org.mtr.resource.VehicleResource;

public record NativeRegistry(RegistrationCounts counts, Map<Key, VehicleResource> resources) {
    public record Key(TransportMode mode, String id) {}
    public static NativeRegistry capture() {
        RegistrationCounts counts = new RegistrationCounts();
        Map<Key, VehicleResource> resources = new LinkedHashMap<>();
        for (TransportMode mode : TransportMode.values()) {
            CustomResourceLoader.iterateVehicles(mode, resource -> {
                counts.add(resource.getId());
                resources.put(new Key(mode, resource.getId()), resource);
            });
        }
        return new NativeRegistry(counts, resources);
    }
}
