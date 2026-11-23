import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Offline adapter over spark's public generated protobuf-lite API.
 * Compile this class separately and supply the exact audited spark JAR on -cp.
 * No Minecraft/plugin initialization, network access, or private-field access.
 */
public final class SparkProfileExport {
    private static final long MAX_INPUT = 32L * 1024 * 1024;

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--self-test")) {
            selfTest();
            return;
        }
        if (args.length != 1) throw new IllegalArgumentException("Supply one local .sparkprofile file");
        Path input = Path.of(args[0]);
        if (Files.size(input) > MAX_INPUT) throw new IllegalArgumentException("Profile exceeds 32 MiB input bound");
        byte[] bytes = Files.readAllBytes(input);
        if (bytes.length > MAX_INPUT) throw new IllegalArgumentException("Profile grew beyond input bound");
        Class<?> data = Class.forName("me.lucko.spark.proto.SparkSamplerProtos$SamplerData");
        Object decoded = data.getMethod("parseFrom", byte[].class).invoke(null, (Object) bytes);
        Object result = convert(decoded, 0);
        PrintWriter output = new PrintWriter(new OutputStreamWriter(System.out, StandardCharsets.UTF_8));
        json(output, result);
        output.println();
        output.flush();
        if (output.checkError()) throw new IllegalStateException("Profile JSON output failed");
    }

    private static Object convert(Object value, int depth) throws Exception {
        if (depth > 64) throw new IllegalArgumentException("Generated message nesting exceeds bound");
        if (value == null || value instanceof String || value instanceof Boolean || value instanceof Number) {
            return value;
        }
        if (value instanceof Enum<?> enumeration) {
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("name", enumeration.name());
            try { out.put("number", value.getClass().getMethod("getNumber").invoke(value)); }
            catch (java.lang.reflect.InvocationTargetException error) {
                if (!enumeration.name().equals("UNRECOGNIZED")) throw error;
                out.put("number", null);
            }
            return out;
        }
        if (value instanceof List<?> list) {
            List<Object> out = new ArrayList<>();
            for (Object item : list) out.add(convert(item, depth + 1));
            return out;
        }
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (var item : map.entrySet()) out.put(String.valueOf(item.getKey()), convert(item.getValue(), depth + 1));
            return out;
        }
        Class<?> type = value.getClass();
        if (type.getName().startsWith("me.lucko.spark.lib.protobuf.ByteString")) {
            Class<?> bytes = Class.forName("me.lucko.spark.lib.protobuf.ByteString");
            byte[] raw = (byte[]) bytes.getMethod("toByteArray").invoke(value);
            return Map.of("protobufBytesBase64", java.util.Base64.getEncoder().encodeToString(raw));
        }
        if (!type.getName().startsWith("me.lucko.spark.proto.") && type != TestMessage.class) {
            throw new IllegalArgumentException("Unexpected generated message type: " + type.getName());
        }
        Map<String, Object> out = new LinkedHashMap<>();
        Method[] methods = type.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::getName));
        for (Method method : methods) {
            String name = method.getName();
            if (!Modifier.isPublic(method.getModifiers()) || Modifier.isStatic(method.getModifiers())
                    || method.isSynthetic() || method.getParameterCount() != 0 || !name.startsWith("get")
                    || name.equals("getDefaultInstanceForType") || name.equals("getParserForType")) continue;
            String base = name.substring(3);
            if (base.endsWith("OrBuilder") || base.endsWith("OrBuilderList")) continue;
            if (base.endsWith("Count") && (has(type, "get" + base.substring(0, base.length() - 5) + "List")
                    || has(type, "get" + base.substring(0, base.length() - 5) + "Map"))) continue;
            if (base.endsWith("Bytes") && has(type, "get" + base.substring(0, base.length() - 5))) continue;
            if (base.endsWith("Value")) {
                Method field = getter(type, "get" + base.substring(0, base.length() - 5));
                if (field != null && field.getReturnType().isEnum()) continue;
            }
            if (!base.endsWith("Map") && !base.endsWith("List")
                    && (has(type, name + "Map") || has(type, name + "List"))) continue;
            if (base.endsWith("Map")) base = base.substring(0, base.length() - 3);
            else if (base.endsWith("List")) base = base.substring(0, base.length() - 4);
            String key = Character.toLowerCase(base.charAt(0)) + base.substring(1);
            if (out.containsKey(key)) throw new IllegalArgumentException("Ambiguous generated field: " + key);
            try { out.put(key, convert(method.invoke(value), depth + 1)); }
            catch (Exception error) { throw new IllegalArgumentException("Generated getter failed: " + type.getName() + "." + name, error); }
        }
        return out;
    }

    private static Method getter(Class<?> type, String name) {
        try { return type.getMethod(name); }
        catch (NoSuchMethodException absent) { return null; }
    }
    private static boolean has(Class<?> type, String name) { return getter(type, name) != null; }

    private static void json(PrintWriter out, Object value) {
        if (value == null) out.print("null");
        else if (value instanceof String text) quote(out, text);
        else if (value instanceof Number number) {
            if ((number instanceof Double && !Double.isFinite(number.doubleValue()))
                    || (number instanceof Float && !Float.isFinite(number.floatValue()))) {
                out.print("{\"nonFinite\":"); quote(out, number.toString()); out.print("}");
            } else out.print(number);
        } else if (value instanceof Boolean) out.print(value);
        else if (value instanceof Map<?, ?> map) {
            out.print('{'); boolean first = true;
            for (var entry : map.entrySet()) {
                if (!first) out.print(','); first = false;
                quote(out, String.valueOf(entry.getKey())); out.print(':'); json(out, entry.getValue());
            }
            out.print('}');
        } else if (value instanceof List<?> list) {
            out.print('[');
            for (int i = 0; i < list.size(); i++) { if (i != 0) out.print(','); json(out, list.get(i)); }
            out.print(']');
        } else throw new IllegalArgumentException("Unsupported JSON value");
    }

    private static void quote(PrintWriter out, String text) {
        out.print('"');
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == '"' || c == '\\') { out.print('\\'); out.print(c); }
            else if (c < 32) out.printf("\\u%04x", (int) c);
            else out.print(c);
        }
        out.print('"');
    }

    public static final class TestMessage {
        public int getPlayerCount() { return -1; }
        public long getStartTime() { return 1794977005615L; }
        public int getThreadsCount() { return 1; }
        public List<String> getThreadsList() { return List.of("Render thread"); }
        public String getComment() { return "line\n\"\\"; }
        public byte[] getCommentBytes() { return new byte[0]; }
    }

    private static void selfTest() throws Exception {
        Object decoded = convert(new TestMessage(), 0);
        if (!(decoded instanceof Map<?, ?> map) || !Integer.valueOf(-1).equals(map.get("playerCount"))
                || !Long.valueOf(1794977005615L).equals(map.get("startTime"))
                || !List.of("Render thread").equals(map.get("threads")) || map.containsKey("threadsCount")
                || map.containsKey("commentBytes")) throw new AssertionError("Generated getter contract failed");
        var buffer = new java.io.StringWriter();
        var writer = new PrintWriter(buffer);
        json(writer, decoded); writer.flush();
        if (!buffer.toString().contains("\\u000a\\\"\\\\")) throw new AssertionError("JSON escaping failed");
        System.out.println("Generated getter, signed integer, int64, repeated-field and JSON escaping controls passed");
    }
}
