"""Parley v2: live-sport parlay construction.

The engine is split so the decision can be tested without an account:

    models    the shapes, validated at the Kalshi boundary
    filters   which legs qualify, and why the rest did not
    combos    partitioning qualified legs into disjoint parlays
    engine    the pass, and the only part that touches the exchange

Import order runs one way only -- engine depends on combos depends on filters
depends on models -- so a change to a threshold cannot reach back into the
shapes.
"""
