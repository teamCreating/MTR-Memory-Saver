# Performance v6 compatibility candidate

Target: NeoForge 21.1.265 / Minecraft 1.21.1 / MTR `4.1.0-beta.2-mc1.21.1-performance-v6`, SHA-256 `8bd419bd798c2ab2fa03e08850409387804fdeb2e4f2987c66b9984236263585`.

The separately built **v0.3.1-v6** candidate carries the v0.3.0 memory features onto this exact custom release. It reads integer ARGB directly, omits the obsolete Color-construction redirect, preserves native build caching/mutation guards and releases a built destination's packed staging data. Shared source groups remain available to independent model facades. A close hook serializes each facade's closure with asynchronous publication; native v6 GPU disposal remains in place.

Thirty companion classes remain byte-identical to delivered v0.3.0, including the resource-text cache, digest, JSON cache and vertex codec helpers. Three classes change, one obsolete mixin is removed and one lifecycle mixin is added. The official-release artifact remains unchanged.

The candidate compiles and passes 1,400,028 synthetic vertex comparisons against the actual v6 methods. Full-pack runtime loading, native GPU ownership, close/reload and repeat acceptance are being recorded separately; this draft does not yet claim runtime acceptance.
