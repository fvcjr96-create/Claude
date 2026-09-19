"""Exact rectangular assignment (Hungarian / Jonker-Volgenant).

Survivor planning is a maximum-weight bipartite matching: each week gets one
team, each team is used at most once, and we maximise the product of win
probabilities.  Taking logs turns that product into a sum, which is exactly
what this solves -- optimally, not greedily.
"""

from __future__ import annotations

# Stand-in for "impossible" that still behaves under addition and subtraction.
# Real log-probability costs are tiny next to this, so any finite assignment
# beats using a forbidden cell, but the arithmetic never produces inf - inf.
BLOCKED = 1e9


def solve(cost: list[list[float]]) -> list[int]:
    """Minimise total cost assigning every row a distinct column.

    `cost` is n x m with n <= m.  Returns a list of length n giving the column
    chosen for each row.  Cells that are not allowed should be set to BLOCKED.
    """
    n = len(cost)
    if n == 0:
        return []
    m = len(cost[0])
    if m < n:
        raise ValueError(f"need at least as many columns as rows ({n} rows, {m} columns)")

    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)      # p[j] = row currently matched to column j
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = -1
            row = cost[i0 - 1]
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = row[j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    out = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            out[p[j] - 1] = j - 1
    return out


def total_cost(cost: list[list[float]], assignment: list[int]) -> float:
    return sum(cost[i][j] for i, j in enumerate(assignment) if j >= 0)
