# Owner answers of 2026-11-20 (lead record)

The owner came back after the absence of D-43 and asked for the open questions. The lead put them to the owner in Arabic
in the live session, through the question dialog. Each item below gives the question, the answer, and what follows.

## OQ-Q101: invariant-7 save order in approve_each_write (B-527, plan 0007 T9b)

Question: does the invariant-7 save (`p~pre.save`) come before the approval preview (`p~pre.approve`) or after it?

ANSWERED by the owner: «الحفظ قبل الموافقة» (the save comes before the approval preview).

Consequences (lead): the engineer approves exactly what will be written and the preview is not voided (AC23). A
documents amendment adds `engine/_ctx_impl.py`, `engine/_modes.py` and `engine/_invariants.py` to plan 0007 T9b,
limited to that ordering, with a cross-reference note in plan 0001; then B-527 continues so that
`test_approvals_per_mode[approve_each_write]` passes.

## OQ-Q102: SAP2000 host table names (B-248)

ANSWERED by the owner: keep them unknown. B-248 stays blocked until an L4 recording or the names are provided; it does
not block the first live run.

## OQ-Q103: the four shipped readings of spec 0010 section 4.9 (B-401)

ANSWERED by the owner: all four shipped readings are confirmed (COMBO_CONFLICT; empty loads and combinations_to_add on
a soft outcome; the equilibrium union with a missing side counted as 0; DOUBLE_MATCH as INVALID_ARGUMENT). Review
again after the first live run if needed.

## OQ-Q104: source of element_id and type_id in the frame element map (B-241, plan 0011 T12)

Options: (a) add a `harness.revit_structure/1` input; (b) retype the elements input; (c) drop the two ids from the
pairs.

ANSWERED by the owner: «مدخل ثانٍ: بنية Revit» (option (a), a second input `harness.revit_structure/1`).

Consequences (lead): a documents amendment of spec 0011 section 4.11 and plan 0011 T12 adds the input as the source of
`element_id` and `type_id` and defines the ambiguous and conflict row schemas; then B-241, then B-286 and B-287.

## OQ-Q98: column demands E3, a single bending moment on a symmetric section (spec 0013 section 4.4.2)

Question: an M2-only case maps to Mu = 0 and Mu_other = M2, so the ACI axial-flexure check returns NOT_APPLICABLE. Put
the sole nonzero moment in Mu for a symmetric section?

ANSWERED by the owner: «نعم، العزم الوحيد في Mu» (yes).

Consequences (lead): a documents amendment of spec 0013 E3 (the sole nonzero moment goes in Mu for a symmetric
section; biaxial bending stays NEEDS_ENGINEER), then a code follow-up of the column demands calc (lead follow-up
L-B282-1).

## OQ-Q93: closing some footings while the others continue (B-399, plan 0010 T8)

The lead explained the question again with an example: in a round of five footings, footing 3 closes (its column is
wider than any allowed size) while the other four continue; how do the calcs see only the open footings? Options: the
block passes the open footings only, or a new version of the merged footing_status calc.

ANSWERED by the owner: «الكتلة تمرر المفتوحة فقط» (option (b), the block passes the open footings only).

Consequences (lead): each round the block stores an open-only design record that the layout, status and resize calcs
read; a closed footing keeps its last result aside; no merged and verified calc changes. A documents amendment of spec
0010 section 4.6 and plan 0010 T8 records the rule, then B-399 continues on its branch.
