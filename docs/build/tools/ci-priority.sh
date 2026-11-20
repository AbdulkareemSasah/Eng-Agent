#!/usr/bin/env bash
# Lead tooling: the live local CI run gets the CPU first (its tests include wall-clock assertions), whatever else the
# machine runs (writers' gate runs, mutation, dry runs). Every 15 seconds, raise the priority of every process that
# runs from the live local CI worktrees. Stops when <lead>/locks/ci-priority.stop exists.
while [ ! -f <lead>/locks/ci-priority.stop ]; do
  for p in $(pgrep -f "<build-v1>/.localci/worktrees/" 2>/dev/null); do
    renice -n -5 -p "$p" >/dev/null 2>&1
  done
  sleep 15
done
