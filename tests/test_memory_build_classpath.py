"""Prevent cross-version NeoForge client patches from entering companion builds."""
import pathlib
import tempfile
import unittest
import zipfile

from build_vehicle_memory_mod import minecraft_classpath, save_json


class ActiveClientPatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.instance = pathlib.Path(self.temporary.name)
        self.version = '21.1.248'
        self.launch_version = 'neoforge-' + self.version
        save_json(self.instance / 'vehicle-test-instance.json', {
            'loader': self.version, 'version': self.launch_version})
        metadata = self.instance / 'versions' / self.launch_version
        metadata.mkdir(parents=True)
        self.metadata = metadata / (self.launch_version + '.json')
        save_json(self.metadata, {'arguments': {'game': ['--fml.neoForgeVersion', self.version]}})

    def patch(self, version, valid=True):
        jar = self.instance / 'libraries/net/neoforged/neoforge' / version / f'neoforge-{version}-client.jar'
        jar.parent.mkdir(parents=True)
        with zipfile.ZipFile(jar, 'w') as archive:
            archive.writestr('net/minecraft/resources/ResourceLocation.class' if valid else 'unrelated.class', b'')
        return jar

    def test_selects_active_patch_with_another_version_cached(self):
        active = self.patch(self.version)
        self.patch('21.1.265')
        self.assertEqual(minecraft_classpath(self.instance, 'neoforge'), [active])

    def test_missing_active_patch_does_not_fall_back(self):
        self.patch('21.1.265')
        with self.assertRaisesRegex(ValueError, 'missing'):
            minecraft_classpath(self.instance, 'neoforge')

    def test_marker_launch_mismatch_is_rejected(self):
        self.patch(self.version)
        save_json(self.metadata, {'arguments': {'game': ['--fml.neoForgeVersion', '21.1.265']}})
        with self.assertRaisesRegex(ValueError, 'differs'):
            minecraft_classpath(self.instance, 'neoforge')

    def test_wrong_client_patch_is_rejected(self):
        self.patch(self.version, valid=False)
        with self.assertRaisesRegex(ValueError, 'lacks'):
            minecraft_classpath(self.instance, 'neoforge')


if __name__ == '__main__':
    unittest.main()
