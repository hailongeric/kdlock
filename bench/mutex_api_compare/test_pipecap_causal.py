"""VM-only negative checks for original-input diagnostic boundaries."""
import io
import struct
import unittest
from unittest.mock import patch

import run
import pipecap_causal as plan
import route_snapshot as snapshot
from profile_replay import Profile


def observation():
    return dict(timing_enabled=False,started_ns=1,finished_ns=2,
        totals={n:0 for n in snapshot.PERCPU},
        native={n:0 for n in snapshot.GLOBALS if n.startswith('kd_native_')},
        timings={n:dict(samples=0,ns=0,invalid=0) for n in snapshot.PHASES})


class CausalTests(unittest.TestCase):
    def test_fixed_original_rotations_and_mode_separation(self):
        original=run.execution_order(); rows=plan.order(original)
        self.assertEqual(len(rows),48);self.assertEqual(len(set(rows)),48)
        for repeat in range(3):
            arms=[r[3] for r in original if r[:3]==('pipecap',5,repeat)]
            selected=[r for r in rows if r[2]//4==repeat]
            for index in range(0,16,4):
                self.assertEqual([r[3] for r in selected[index:index+4]],arms)
                self.assertEqual(selected[index][2]%4,(repeat+index//4)%4)
        with self.assertRaises(ValueError):plan.order([])

    def test_spec_preserves_all_work_and_required_checks(self):
        base=dict(name='pipecap-t05-r1-public-kd',require_jit=True,cpus=list(range(5)),
                  threads=5,collector_cpu=63,duration_ms=2000,warmup=48000,warmup_ms=1000,
                  source_identity='original',caller_shell='mutex_public_direct',repeat=1)
        def make(*args,**kwargs):
            self.assertEqual(args[3],1)
            return dict(base)
        for i,mode in enumerate(plan.MODES):
            result=plan.specification(make,(None,'pipecap',5,4+i,'public-kd',None,None),{},'perf')
            self.assertEqual({k:result[k] for k in base if k!='name'},
                             {k:v for k,v in base.items() if k!='name'})
            self.assertTrue(result['name'].endswith('-'+mode))
            self.assertEqual(result['inclusive_jit_timing'],mode=='timing')
            self.assertFalse(result['score_eligible'])
        with self.assertRaises(RuntimeError):Profile(None,'perf',clock_id='realtime')
        self.assertIsNone(Profile(None,'perf').clock_id)
        self.assertEqual(Profile(None,'perf',clock_id='mono').clock_id,'mono')

    def test_symbols_reject_duplicates_missing_and_wrong_module(self):
        text='ffffffff82900000 D __per_cpu_offset\nffffffff82900100 D __pgtable_l5_enabled\n'+'\n'.join(
            f'0000000000036000 a {n} [kdlock_km]' for n in snapshot.PERCPU | snapshot.GLOBALS)
        self.assertEqual(set(snapshot.parse_symbols(text)),set(snapshot.PERCPU)|set(snapshot.GLOBALS)|{'__per_cpu_offset','__pgtable_l5_enabled'})
        for invalid in (text+'\nffffffff82900000 D __per_cpu_offset',
                        text.replace('kd_mutex_slowpath_count','unrelated_count'),
                        text.replace('[kdlock_km]','[another_module]')):
            with self.assertRaises(ValueError):snapshot.parse_symbols(invalid)

    def test_timing_rejects_overflow_invalid_and_wrong_extent(self):
        raw=struct.pack('<qqi4x',2,102,0)*10
        self.assertEqual(snapshot.decode_timing(raw)['mutex_queue'],dict(samples=2,ns=102,invalid=0))
        for bad in (raw[:-1],struct.pack('<qqi4x',-1,1,0)*10,
                    struct.pack('<qqi4x',1,-1,0)*10,struct.pack('<qqi4x',1,1,1)*10):
            with self.assertRaises(ValueError):snapshot.decode_timing(bad)

    def test_retained_client_clock_schema_and_overlap_refusal(self):
        measured=dict(started_ns=20,finished_ns=40,workers=[
            dict(active_started_ns=21,finished_ns=39),
            dict(active_started_ns=22,finished_ns=40)])
        plan.validate_measurement_bounds(dict(finished_ns=19),dict(started_ns=41),measured)
        for before,after in ((21,41),(19,39)):
            with self.assertRaises(ValueError):
                plan.validate_measurement_bounds(dict(finished_ns=before),dict(started_ns=after),measured)
        measured['workers'][0]['active_started_ns']=41
        with self.assertRaises(ValueError):
            plan.validate_measurement_bounds(dict(finished_ns=19),dict(started_ns=42),measured)

    def test_delta_refuses_decrease_policy_change_or_reversed_boundary(self):
        before,after=observation(),observation();after.update(started_ns=3,finished_ns=4)
        before['totals']['kd_hotlock_mutex_entries']=1024
        after['totals']['kd_bench_bodies']=7
        self.assertEqual(snapshot.difference(before,after)['counters']['kd_bench_bodies'],7)
        self.assertNotIn('kd_hotlock_mutex_entries',snapshot.difference(before,after)['counters'])
        for key in ('timing','order','counter'):
            changed=observation();changed.update(started_ns=3,finished_ns=4)
            if key=='timing':changed['timing_enabled']=True
            elif key=='order':changed['started_ns']=0
            else:changed['totals']['kd_bench_bodies']=-1
            with self.assertRaises(ValueError):snapshot.difference(before,changed)

    def test_kcore_rejects_unmapped_ambiguous_and_short_reads(self):
        core=snapshot.Kcore.__new__(snapshot.Kcore)
        core.kernel_floor=0xffff800000000000
        base=0xffff888000000000
        core.segments=[dict(address=base,size=16,file_size=16,offset=0)]
        core.stream=io.BytesIO(b'0123456789abcdef')
        self.assertEqual(core.read(base+2,4),b'2345')
        for address,size in ((base+15,2),(0,1),(base,0),(base,1024*1024+1)):
            with self.assertRaises(ValueError):core.read(address,size)
        core.segments*=2
        with self.assertRaises(ValueError):core.read(base,4)
        core.segments=core.segments[:1];core.stream=io.BytesIO(b'1')
        with self.assertRaises(ValueError):core.read(base,4)

    def test_five_level_addresses_require_live_enabled_flag_and_retained_mapping(self):
        core=snapshot.Kcore.__new__(snapshot.Kcore)
        high=0xffff888000000000; extended=0xff11000333600000
        core.kernel_floor=0xffff800000000000
        core.segments=[dict(address=high,size=4,file_size=4,offset=0),
                       dict(address=extended,size=4,file_size=4,offset=4)]
        core.stream=io.BytesIO(struct.pack('<II',1,123))
        with self.assertRaises(ValueError):core.read(extended,4)
        self.assertEqual(core.configure_paging(high)['virtual_address_bits'],57)
        self.assertEqual(int.from_bytes(core.read(extended,4),'little'),123)
        with self.assertRaises(ValueError):core.read(extended+4,4)
        core.stream=io.BytesIO(struct.pack('<II',0,123))
        self.assertEqual(core.configure_paging(high)['virtual_address_bits'],48)
        with self.assertRaises(ValueError):core.read(extended,4)
        core.stream=io.BytesIO(struct.pack('<II',2,123))
        with self.assertRaises(ValueError):core.configure_paging(high)

    def test_unstable_snapshot_rejected_and_provider_pin_closed(self):
        reader=snapshot.Snapshot.__new__(snapshot.Snapshot)
        with patch.object(snapshot.os,'open',return_value=17),patch.object(snapshot.os,'close') as close:
            with patch.object(reader,'read',side_effect=[{'count':1},{'count':2}]):
                with self.assertRaises(ValueError):reader.capture()
            close.assert_called_once_with(17)


if __name__ == '__main__':
    unittest.main()
