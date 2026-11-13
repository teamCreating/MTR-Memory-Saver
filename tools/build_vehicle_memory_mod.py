"""Build a named stable target with Gradle; historical instance builds require --legacy."""
import argparse
import os
import pathlib
import subprocess
import sys

# The development build never calls these read-only historical fixture helpers.
from legacy.build_vehicle_memory_mod import (RELEASES, PERFORMANCE_V6, JAVA_PACKAGE,
    RESOURCE_ROOT, MOD_NAME, digest, read_json, save_json, minecraft_classpath, runtime_libraries)

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = next(line.partition('=')[2].strip() for line in
               (ROOT / 'gradle.properties').read_text().splitlines() if line.startswith('modVersion='))


def main():
    if '--legacy' in sys.argv:
        sys.argv.remove('--legacy')
        from legacy.build_vehicle_memory_mod import main as legacy_main
        legacy_main()
        return
    matrix = read_json(ROOT / 'config/targets.json')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=matrix['targets'], default=matrix['default'])
    parser.add_argument('--mtr-jar', type=pathlib.Path, help='Audited custom JAR for v6; optional offline official input.')
    parser.add_argument('--java-home', type=pathlib.Path, help='Java 21 JDK toolchain override.')
    parser.add_argument('--release', action='store_true', help='Create the installable release bundle.')
    args = parser.parse_args()
    command = [str(ROOT / ('gradlew.bat' if os.name == 'nt' else 'gradlew')),
               'releaseBundle' if args.release else 'build', '-Ptarget=' + args.target]
    if args.mtr_jar:
        command.append('-PmtrJar=' + str(args.mtr_jar.resolve()))
    if args.java_home:
        command.append('-Dorg.gradle.java.home=' + str(args.java_home.resolve()))
    raise SystemExit(subprocess.call(command, cwd=ROOT))


if __name__ == '__main__':
    main()
