# A round, concretely

**Before round one**

1. Write the adversary sentence. If it names nobody, stop
   and run correctness review instead.
2. Declare the token ceiling and check whether the fix
   domain is enumerable.
3. Quote the cost and get the go-ahead. With no operator to
   ask, record the declared ceiling in `rounds.json` anyway,
   as `token_ceiling_per_high`, and proceed, so the budget
   clause (7) can be evaluated.
4. Start `rounds.json`.

**Each round**

5. Run the cheap channels first: corpus, mutation sweep,
   recipient read. Fix what they find before dispatching
   agents.
6. Pick lenses by measured yield. Pair each with its
   inverse. Give reviewers the ability to execute.
7. Drop low-severity claims. Dedupe by fix site. Adjudicate
   the rest yourself rather than buying a refutation phase.
8. Read the survivors for **shape** before triaging any of
   them.
9. Triage against product risk. Fix a subset. Write real
   limits into the contract and pin them with tests.
10. Record the round. Run `round_yield.py`. If it says STOP,
    stop, and tell the operator with the curve attached.

**The two moments to speak up**

- When the findings share one shape: say the fix is a design
  change, before spending the round patching cases.
- When the curve goes flat: say it the first time, with the
  numbers, and let the operator decide whether to keep
  paying.
