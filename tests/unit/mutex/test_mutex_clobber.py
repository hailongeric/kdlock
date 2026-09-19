"""Exercise the actual mutex caller macro and ABI-2 wrapper with poisoned GPRs.

The common fixture also mixes legacy generated bodies, materializes FULL service
exits and checks high-pressure caller values across destructive lock/unlock calls.
"""
from test_spin_clobber import main

if __name__ == "__main__":
    main(entry_abi=2)
