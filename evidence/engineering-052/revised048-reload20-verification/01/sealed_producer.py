"""Construct the frozen importer using only sealed and lexical recorded paths."""
import hashlib
import json
from pathlib import PureWindowsPath

def create_producer(core, base):
    def read(path): return json.loads(path.read_bytes())
    def sha(raw): return hashlib.sha256(raw).hexdigest()
    def check(value, message):
        if not value: raise ValueError(message)
    class SealedProducer(core.FrozenProducer):
        def __init__(self, recorder, consumer):
            self.recorder, self.consumer = recorder.resolve(), consumer.resolve()
            self.sources = self.recorder / 'sources'
            self.context = read(self.recorder / 'session-start.json')
            self.plan = read(self.recorder / 'packaged-client-plan.json')
            self.launch = read(self.recorder / 'packaged-client-launch.json')
            self.metadata = read(self.consumer / 'observer-target.json')
            self.review = read(self.consumer / 'native-diagnostic-review.json')
            paths = [self.recorder / x for x in ['session-start.json','packaged-client-plan.json','packaged-client-launch.json','native-diagnostic-review.json']]
            paths += [self.consumer / x for x in ['observer-target.json','native-diagnostic-review.json']]
            self.pins = {path: sha(path.read_bytes()) for path in paths}
            for original, expected in self.context['source_sha256'].items():
                filename = PureWindowsPath(original).name
                self.pins[self.sources / filename] = expected
                self.pins[self.consumer / ('observer-source.py' if filename == 'observe_packaged_client.py' else filename)] = expected
            self.check_sources()
            recorded, planned = PureWindowsPath(self.context['instance']), PureWindowsPath(self.plan['instance'])
            check(recorded.is_absolute() and '..' not in recorded.parts and recorded == planned, 'Recorded lexical instance identity differs')
            check(self.metadata == self.context['metadata'] and self.review == read(self.recorder/'native-diagnostic-review.json'), 'Target/review differs')
            check(sha((self.recorder/'packaged-client-plan.json').read_bytes()) == self.context['plan_sha256'] == self.launch['plan_sha256'], 'Plan pin differs')
            check(sha((self.recorder/'packaged-client-launch.json').read_bytes()) == self.context['launch_sha256'] and self.launch['pid'] == self.context['process']['pid'], 'Launch/process pin differs')
    return SealedProducer(base/'recorder',base/'observer')
