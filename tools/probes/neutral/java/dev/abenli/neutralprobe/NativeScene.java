package dev.abenli.neutralprobe;

import dev.abenli.neutralprobe.mixin.NativeClientDataAccess;
import dev.abenli.neutralprobe.mixin.VehicleCacheAccess;
import dev.abenli.neutralprobe.mixin.VehicleProgressAccess;
import java.util.LinkedHashSet;
import net.minecraft.client.Minecraft;
import net.minecraft.world.phys.AABB;
import org.mtr.libraries.com.google.gson.JsonArray;
import org.mtr.libraries.com.google.gson.JsonNull;
import org.mtr.libraries.com.google.gson.JsonObject;

/** Reads existing simulation and cache data without requesting positions/baking. */
public final class NativeScene {
    private NativeScene() {}
    public static void capture(JsonObject result, Minecraft mc, NativeRegistry registry) {
        if (mc.level == null) {
            result.add("world", JsonNull.INSTANCE);
            result.add("train_state", JsonNull.INSTANCE);
            result.add("cache_state", JsonNull.INSTANCE);
            return;
        }
        JsonObject world = new JsonObject();
        world.addProperty("dimension", mc.level.dimension().location().toString());
        world.addProperty("game_time", mc.level.getGameTime());
        if (mc.player == null) world.add("player", JsonNull.INSTANCE);
        else {
            JsonObject player = new JsonObject();
            player.addProperty("x", mc.player.getX());
            player.addProperty("y", mc.player.getY());
            player.addProperty("z", mc.player.getZ());
            player.addProperty("yaw", mc.player.getYRot());
            player.addProperty("pitch", mc.player.getXRot());
            world.add("player", player);
        }
        result.add("world", world);
        var nativeData = NativeClientDataAccess.neutralInstance();
        if (nativeData == null) {
            result.add("train_state", JsonNull.INSTANCE);
            result.add("cache_state", JsonNull.INSTANCE);
            return;
        }
        var referenced = new LinkedHashSet<NativeRegistry.Key>();
        JsonArray vehicles = new JsonArray();
        for (var vehicle : nativeData.vehicles) {
            JsonObject train = new JsonObject();
            train.addProperty("id", vehicle.getId());
            train.addProperty("transport_mode", vehicle.getTransportMode().name());
            train.addProperty("speed", vehicle.getSpeed());
            train.addProperty("rail_progress", ((VehicleProgressAccess) vehicle).neutralRailProgress());
            train.addProperty("door_value", vehicle.persistentVehicleData.getDoorValue());
            train.addProperty("reversed", vehicle.getReversed());
            var extra = vehicle.vehicleExtraData;
            train.addProperty("route_id", extra.getThisRouteId());
            train.addProperty("platform_id", extra.getThisPlatformId());
            train.addProperty("station_id", extra.getThisStationId());
            train.addProperty("route_name", extra.getThisRouteName());
            train.addProperty("station_name", extra.getThisStationName());
            JsonArray cars = new JsonArray();
            for (var car : extra.immutableVehicleCars) {
                cars.add(car.getVehicleId());
                referenced.add(new NativeRegistry.Key(vehicle.getTransportMode(), car.getVehicleId()));
            }
            train.add("car_resources", cars);
            vehicles.add(train);
        }
        JsonObject trains = new JsonObject();
        trains.addProperty("available", true);
        trains.add("vehicles", vehicles);
        result.add("train_state", trains);

        JsonArray resources = new JsonArray();
        for (var key : referenced) {
            JsonObject resource = new JsonObject();
            resource.addProperty("transport_mode", key.mode().name());
            resource.addProperty("resource_id", key.id());
            var nativeResource = registry.resources().get(key);
            resource.addProperty("registered", nativeResource != null);
            JsonArray entries = new JsonArray();
            if (nativeResource != null) {
                for (var cache : ExistingCaches.entries(((VehicleCacheAccess) (Object) nativeResource).neutralExistingCaches())) {
                    JsonObject entry = new JsonObject();
                    // Official non-legacy resources normalize both native keys
                    // to zero. Preserve observed keys, without guessing a car.
                    entry.addProperty("car_key", cache.carKey());
                    entry.addProperty("total_cars_key", cache.totalCarsKey());
                    entry.add("floors", boxes(cache.value().floors));
                    entry.add("doorways", boxes(cache.value().doorways));
                    entries.add(entry);
                }
            }
            resource.add("entries", entries);
            resources.add(resource);
        }
        JsonObject caches = new JsonObject();
        caches.addProperty("available", true);
        caches.add("resources", resources);
        result.add("cache_state", caches);
    }
    private static JsonArray boxes(Iterable<AABB> boxes) {
        JsonArray array = new JsonArray();
        for (AABB box : boxes) {
            JsonObject value = new JsonObject();
            value.addProperty("min_x", box.minX); value.addProperty("min_y", box.minY); value.addProperty("min_z", box.minZ);
            value.addProperty("max_x", box.maxX); value.addProperty("max_y", box.maxY); value.addProperty("max_z", box.maxZ);
            array.add(value);
        }
        return array;
    }
}
