"""Super-research: market-wide GEX, econ, earnings and the signal ledger.

The whole surface is MARKET DATA rather than operator data. A SPY gamma wall
is the same number for every operator on the desk, so these tables carry no
tenant_id -- the same reasoning that exempts Signal, applied to the same kind
of fact. What IS per-operator is who may see it (a session) and who may arm
the engines behind it (an admin), and that lives at the edge.
"""
