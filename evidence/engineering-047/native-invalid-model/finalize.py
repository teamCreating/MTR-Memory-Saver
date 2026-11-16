"""Summarize saved static evidence and bind every output; no game or Git action."""

import datetime
import pathlib

from attribute import OUT, MTR_SHA, sha, load, write, find_line


def main():
    registry = load((OUT / "assessment.json").read_bytes())
    legacy = load((OUT / "legacy-directory-assessment.json").read_bytes())
    inputs = load((OUT / "rail-consumption-inputs.json").read_bytes())
    texts = {row["entry"]: (OUT / row["javap"]).read_text(encoding="utf-8") for row in inputs}
    render = texts["org/mtr/render/RenderRails.class"]
    sound = texts["org/mtr/sound/VehicleSoundBase$RunSoundInfo.class"]
    loader = texts["org/mtr/model/BlockbenchModelLoader.class"]
    rail = (OUT / "org.mtr.resource.RailResource.javap.txt").read_text(encoding="utf-8")
    converter = (OUT / "org.mtr.legacy.resource.CustomResourcesConverter.javap.txt").read_text(encoding="utf-8")
    assert "112: ifeq          123" in render and "120: goto          152" in render
    assert "149: invokestatic" in render and "136: invokevirtual" in render and "RailResource.render:" in render
    assert "getDefaultRail3D:" in render and "// String default_3d" in render
    assert "getIdWithoutDirection(java.lang.String)" in rail and "// String _1" in rail and "// String _2" in rail
    assert "getSoundIndex:" in sound and "getOptimizedModel" not in sound and "modelLoaderBase" not in sound
    assert "parseStarted:" in loader and "submit:" in loader and "canLoadModel:" in loader
    assert "// String mtrsteamloco" in converter and "// String .json" in converter
    assert registry["unsupported_suffix_authored_candidates"] == 0
    assert not legacy["unsupported_suffix_candidates"]
    timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    assessment = {
        "timestamp": timestamp, "target": "official MTR 4.1.0-beta.2", "archive_sha256": MTR_SHA,
        "status": "static_default_rail_functional_boundary_not_runtime_validation",
        "registry_assessment_sha256": sha(OUT / "assessment.json"),
        "legacy_directory_assessment_sha256": sha(OUT / "legacy-directory-assessment.json"),
        "bytecode_inputs": [{**row, "javap_sha256": sha(OUT / row["javap"])} for row in inputs],
        "exact_default_style": {
            "method": "org.mtr.render.RenderRails.renderRailStandard",
            "config_mapping": "Only getDefaultRail3D=true with transportMode=TRAIN maps exact default to default_3d or default_3d_siding. Other styles remain unchanged.",
            "two_dimensional_branch": "Final style exactly equal to default sets boolean[0] and jumps from bytecode 120 to 152, bypassing getRailById at 149. The later basic rendering path uses supplied RAIL_TEXTURE/RAIL_PREVIEW_TEXTURE rather than this RailResource model.",
            "evidence_file": "org.mtr.render.RenderRails.javap.txt",
            "evidence_lines": find_line(render, "getDefaultRail3D:") + find_line(render, "112: ifeq") + find_line(render, "120: goto") + find_line(render, "149: invokestatic")},
        "direction_suffix_boundary": {
            "styles": ["default_1", "default_2"],
            "behavior": "These fail the exact default comparison and enter the custom-model branch. RailResource.getIdWithoutDirection strips _1/_2, allowing lookup of the default resource, followed by RailResource.render. Actual UI selectability, authored world styles, and runtime occurrence remain unverified.",
            "evidence_files": ["org.mtr.resource.RailResource.javap.txt", "org.mtr.render.RenderRails.javap.txt"],
            "strip_method_line": find_line(rail, "getIdWithoutDirection(java.lang.String)")[0],
            "render_call_line": find_line(render, "RailResource.render:")[0]},
        "sound_consumer": {
            "method": "org.mtr.sound.VehicleSoundBase$RunSoundInfo.create",
            "behavior": "Looks up the first current/previous style and reads RailResource.getSoundIndex. No model factory, optimized model, or model render call occurs in this saved class.",
            "evidence_file": "org.mtr.sound.VehicleSoundBase$RunSoundInfo.javap.txt",
            "evidence_lines": find_line(sound, "getRailById:") + find_line(sound, "getSoundIndex:")},
        "fallback_work_boundary": {
            "behavior": "VehicleModel unsupported-format fallback calls BlockbenchModelLoader.loadModel with an empty-JSON model supplier. Its canLoadModel path calls parseStarted and submits a worker task. shouldPreload=false controls later preload selection; it does not imply no construction or asynchronous parsing work.",
            "evidence_file": "org.mtr.model.BlockbenchModelLoader.javap.txt",
            "evidence_lines": find_line(loader, "canLoadModel:") + find_line(loader, "parseStarted:") + find_line(loader, "submit:")},
        "combined_authored_audit": {
            "verified_archives": 17, "registry_model_consumers": registry["model_consumer_rows_audited"],
            "legacy_directory_model_consumers": legacy["model_consumers_audited"],
            "total_model_consumers": registry["model_consumer_rows_audited"] + legacy["model_consumers_audited"],
            "unsupported_suffix_candidates": 0,
            "meaning": "No audited authored registry or directory-migration model field enters the factory's unsupported-format branch. This is suffix attribution, not parsing/rendering/texture validation or runtime registration-count validation."},
        "independent_review": "rail_branch_review independently checked the generated default call chain, exact-style rendering bypass, direction-suffix counterexample, sound-only consumer, and fallback worker boundary using saved official bytecode. It also independently enumerated all 17 archives, reconstructed the 17 directory entries and 303 model consumers, and confirmed native map-ID lowercasing and unchanged model copying. No client action was part of this review.",
        "limits": [
            "The native generated source is statically proven. Individual archived log occurrences have no runtime stack trace; a mod-free baseline was not run here.",
            "No claim of harmlessness, zero overhead, absence of behavior regressions, or unique runtime source follows from these branches.",
            "No route, endurance, reload-cycle, or performance pass is claimed. In particular, this evidence does not qualify or reinterpret the separate route03 run.",
        ],
        "script_sha256": sha(pathlib.Path(__file__)),
    }
    write("rail-consumption-assessment.json", assessment)
    readme = f"""# 官方 Invalid model 静态归因

证据时间：{timestamp}（UTC+08:00）。范围仅官方 MTR 4.1.0-beta.2，未验证 v6。

已定位官方 JAR 的程序生成源：`CustomResourceLoader.reload()` 在读取任何 registry 前创建轨道 `id=default`、`name=Default`，其便捷构造传入空 `modelResource` 和空 `textureResource`，随后调用 `VehicleModel.getModelLoaderBase()`。工厂先格式化纹理，再对原始模型字段检查 `.bbmodel`/`.obj` 后缀；错误分支打印的是纹理标识。因此这条路径会打印 `[mtr:textures/block/transparent.png] Invalid model!`，日志本身不证明 PNG 损坏。

原始 archive SHA：`{MTR_SHA}`。生成调用所在 entry：`org/mtr/client/CustomResourceLoader.class`，entry SHA：`ec7cfc6da67a42332c1cc3f89e0b5db5c0d7df4c657f3267ef82346b1dd28934`。该 ID 来自 class 字面量，无 registry entry 或 JSON pointer。

官方 JAR 加 16 包全部按准备计划和 catalogue 校验 SHA。两个 registry 共审计 4,200 个模型消费项，另按官方目录迁移规则审计 303 个旧格式项（289 对象、14 轨道），总计 4,503 项；没有不支持后缀的 authored 候选。每项保留 archive SHA、entry SHA、ID、JSON pointer 和原始模型/纹理字段。两个目录 JSON 来自 source 10 的 `assets/mtrsteamloco/eyecandies/mcav2.json` 与 source 15 的 `assets/mtrsteamloco/rails/guotie.json`。七个 sign-only legacy 声明单独记录，不混入模型消费计数。

功能边界：最终 style 精确为 `default` 时，官方二维绘制绕过该轨道模型；启用默认 3D 且为 TRAIN 时，精确 `default` 会映射至 `default_3d` 或 `default_3d_siding`。但是 `default_1/default_2` 可通过剥离方向后缀 lookup `default` 并进入模型渲染，是否实际可选或存在于世界尚未验证。声音路径仅读取 `soundIndex`。空模型 fallback 仍可能提交解析 worker；`shouldPreload=false` 不代表零开销。

这是静态来源与分支证据。未启动客户端、安装观察器、重载资源、修改实例或操作 UI；没有追踪具体日志行的运行时调用栈，也没有完成无 companion 基线。不得将其改写为 PNG 损坏、唯一运行时来源、无害噪音或游戏验收通过。

主要文件：`assessment.json`（来源、原生调用链和 registry 审计）、`legacy-directory-assessment.json`（目录消费者）、`rail-consumption-assessment.json`（功能边界）、相应 `*.javap.txt` 和模型消费明细。`sha256.json` 绑定本目录全部最终文件，排除自身。
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    write("sha256.json", {path.name: sha(path) for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "sha256.json"})
    print({"files_bound": len(load((OUT / "sha256.json").read_bytes())), "manifest_sha256": sha(OUT / "sha256.json")})


if __name__ == "__main__":
    main()
