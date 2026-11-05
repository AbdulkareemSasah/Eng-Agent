# Local testing: structural-codes

The core needs no host program. The ACI 318-14 pack (plan 0002) needs the program comparisons below; none is claimed
as done, and every row is run by the owner.

| Item | Host | What is compared |
|---|---|---|
| PC-1 bearing | SAFE | Soil pressure under a service combination for the bearing HC-2 footing |
| PC-1 one-way shear | SAFE | One-way shear at `d` from the face, if SAFE reports it for footings |
| PC-1 punching | SAFE | Punching shear ratio of the punching HC-1 footing, assumption differences listed |
| PC-1 flexure | SAFE | Strip moment at the column face for the flexure HC-2 footing |
| PC-1 minimum reinforcement | SAFE | Minimum steel in footing strips |
| Reaction convention | ETABS or SAFE | Signs of `FX`, `FY`, `MX`, `MY` in `forces.joint_reactions/1`, which FS S2 combines with the reaction height |

## SBC 304-2018 pack (plan 0003)

No item needs a host program in this version: the pack evaluates no SBC equation and every check returns
`NEEDS_ENGINEER`. Program comparisons are added by the pull request that turns a clause-map row to `inherited`.
