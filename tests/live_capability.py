"""Opt-in real Docker + Ed25519 adoption check; toy scores/actors are labelled fixtures."""
import argparse
import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hci import CapabilityTests
from gresearch import attestation, capabilities as cap
from gresearch.core import ResearchError, canonical, fingerprint, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Immutable Docker image digest with python3')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    fixture = CapabilityTests()
    fixture.setUp()
    try:
        candidate, incumbent, protocol, source = fixture.setup_capability()
        keys = attestation.keygen(fixture.root / 'evaluator-keys')
        protocol.update(isolation={'kind': 'docker', 'image': args.image, 'memory_mb': 256},
                        attestation={'public_key': keys['public_key']}, timeout=45, trial_seconds=240)
        with mock.patch.dict(os.environ, {'GRESEARCH_SIGNING_KEY': keys['private_key_path']}):
            cap.freeze(fixture.store, fixture.target, 'signed', protocol, fixture.root / 'evaluator', incumbent, ['{python}', 'agent.py'],
                       actor='scripted-proposer', reason='Live Docker integration fixture', reviewers=['scripted-reviewer'])
            proposal = cap.propose(fixture.store, fixture.target, 'signed', candidate, ['{python}', 'agent.py'],
                                   actor='scripted-proposer', reason='Toy interface fixture, not explanation efficacy', sources=[source])
            trial = cap.evaluate(fixture.store, proposal['id'])
            if not trial['passed']: raise RuntimeError(canonical(trial['reasons']))
            cap.review(fixture.store, proposal['id'], trial['id'], actor='scripted-reviewer', decision='approve', reason='Scripted review')
            # A signed successful trial must not survive corruption of its measurement.
            saved = fixture.store.get_value('rsi:signed')
            corrupted = copy.deepcopy(saved)
            corrupted['trials'][-1]['analysis']['mean_gain'] = 999
            with fixture.store.tx(): fixture.store.set_value('rsi:signed', corrupted)
            tampering_rejected = False
            try:
                cap.review(fixture.store, proposal['id'], trial['id'], actor='scripted-reviewer', decision='approve', reason='Corruption probe')
            except ResearchError:
                tampering_rejected = True
            with fixture.store.tx(): fixture.store.set_value('rsi:signed', saved)
            adopted = cap.activate(fixture.store, proposal['id'], expected_revision=0, actor='scripted-reviewer', reason='Scripted adoption')
        envelope = cap.proposal(fixture.store, proposal['id'])['adoption_attestation']
        expected = {'epoch': 'signed', 'trial': trial['id'], 'protocol_hash': proposal['protocol_hash'],
                    'evaluator_hash': proposal['evaluator_hash'], 'candidate_hash': proposal['candidate_hash']}
        accepted = attestation.accept(fixture.store, envelope, keys['public_key'], expected)
        replay_rejected = False
        try: attestation.accept(fixture.store, envelope, keys['public_key'], expected)
        except ResearchError: replay_rejected = True
        containers = [o['run'] for o in trial['observations']]
        result = {'time_utc': datetime.now(timezone.utc).isoformat(), 'image': args.image,
                  'fixture_only': True, 'human_feedback': 'scripted fixture', 'scientific_gain_claimed': False,
                  'real_container_runs': len(containers), 'containers': containers,
                  'passed_audit': trial['passed'], 'mean_gain_toy_fixture': trial['analysis']['mean_gain'],
                  'public_key': keys['public_key'], 'evaluation_attestation': trial['attestation'],
                  'adoption_attestation': envelope, 'adopted': adopted, 'accepted': accepted,
                  'replay_rejected': replay_rejected, 'measurement_tampering_rejected': tampering_rejected,
                  'store_verified': fixture.store.verify()['valid']}
        result['passed'] = all((trial['passed'], replay_rejected, tampering_rejected, result['store_verified'],
                                all(c['status'] == 'completed' and c['container_removed'] for c in containers)))
        write_json(args.report, result)
        print(canonical({k: result[k] for k in ('passed', 'real_container_runs', 'replay_rejected', 'measurement_tampering_rejected')}))
        return 0 if result['passed'] else 1
    finally:
        fixture.tearDown()


if __name__ == '__main__': raise SystemExit(main())
