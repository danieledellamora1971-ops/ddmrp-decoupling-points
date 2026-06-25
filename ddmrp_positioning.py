"""
Presentation Notes — DDMRP Algorithm for Decoupling Point Positioning

1. Introduction to DDMRP
Demand Driven Material Requirements Planning (DDMRP) is a supply chain planning
and control methodology developed in 2011 by Ptak and Smith as a critical evolution
of traditional MRP/ERP systems. The core problem DDMRP aims to solve is the so-called
bullwhip effect: in a classical MRP system, a small fluctuation in final demand
progressively amplifies upstream through the bill of materials, causing oversized
inventory, stockouts, and perceived lead times that are far too long.

DDMRP departs from the push logic of MRP (which "pushes" orders based on forecasts)
by introducing five operational components: strategic buffer positioning (the focus
of our code), buffer zone sizing (Red/Yellow/Green), dynamic adjustments, demand-driven
planning, and visible and collaborative execution. The conceptual core is simple:
instead of planning everything from the finished good, decoupling points are deliberately
inserted along the bill of materials — nodes where the supply chain is "broken" by a
stock buffer. Upstream of the buffer, the system operates in push logic (to replenish
stock); downstream, it operates in pull logic (to satisfy real demand). In this way,
uncertainty no longer propagates in a cascading fashion, but is absorbed locally.

2. Decoupling Points
A decoupling point is a BOM item to which an actively managed stock buffer is assigned.
Its function is twofold: it protects downstream levels from supply or production
uncertainties (lead time variability, quality issues, supplier reliability), and it
compresses the cumulative lead time perceived by the customer, because when an order
arrives, it is no longer necessary to wait for the entire supply chain — only for the
segment from the nearest decoupling point to the finished good.

The choice of where to position these points is not arbitrary: buffering too many items
ties up capital and increases carrying costs; buffering too few items exposes the company
to stockouts and unacceptable lead times. DDMRP provides a structured methodology based
on six strategic factors: Customer Tolerance Time (CTT) — how long the customer is willing
to wait; external variability of demand and supply; component commonality — a component
used by many parents deserves a buffer because it protects multiple flows simultaneously;
protection of critical operations; and lead time compression toward the finished good.

3. The Positioning Algorithm: Two Phases
The code implements a two-phase algorithm that operationalizes the DDMRP principles.
Phase 1 (Protection) identifies purchased items whose cumulative lead time — computed
as the longest chain connecting them to raw materials — exceeds the customer's CTT, or
that exhibit high supply variability. These items represent a structural risk: if not
buffered, every customer order would have to wait for the entire procurement cycle.

Phase 2 (Compression) intervenes only if, after Phase 1, the Decoupled Lead Time (DLT)
of the finished good remains above the CTT. In this case, the algorithm iteratively
searches for the best item to buffer, evaluating for each candidate both the effective
reduction in the finished good's DLT and a strategic score combining individual lead time,
commonality, variability, and the item's nature. The iteration stops as soon as the
finished good's DLT drops below the CTT, or when no useful candidates remain.

4. How the Code Works: A Numerical Example
To understand the concrete behavior, consider the demo BOM, which represents a finished
good (FG) assembled from two sub-assemblies (SA1, SA2), which in turn use purchased
components (C1, C2, C3) and a raw material (MP1). The customer CTT is set to 12 days.

The first step is computing the cumulative lead time of each item. For MP1 the cumulative
LT is 15 days (only its own LT). For C1 it is 23 days (8 + 15 from MP1). For C3 it is 20
days. For SA1 it is 28 days (5 + 23 from C1, the longest branch between C1 and C2). For
SA2 it is 30 days (7 + 23 from C1). For FG it is 33 days (3 + 30 from SA2). Since 33 is
much greater than the CTT of 12, it is clear that without buffers the customer would have
to wait more than a month.

In Phase 1, the code selects all items with source="buy" and computes their cumulative LT.
MP1 (15 > 12), C3 (20 > 12), and C1 (23 > 12) exceed the threshold and are buffered. C2
instead has a cumulative LT of 6 days and low supply variability (0.3), so it is skipped.
The has_buffered_ancestor function prevents redundant buffering when an upstream buffer
already protects the item and supply variability is not critical.

At the end of Phase 1, the code recomputes the FG's DLT using decoupled_lt(root,
respect_buffers=True). This function traverses the BOM depth-first and, every time it
encounters a buffered child, stops counting lead time. The result is: SA1 contributes 11
days (5 + 6 from C2, because C1 is now buffered and contributes 0); SA2 contributes 7 days
(both C1 and C3 are buffered); FG contributes 3 + max(11, 7) = 14 days. Since 14 is still
greater than 12, Phase 2 is triggered.

Phase 2 heuristically tests each non-buffered candidate. If SA1 is buffered, the FG DLT
drops from 14 to 7 (reduction of 7 days). If C2 is buffered, the DLT drops to 10 (reduction
of 4 days). If SA2 is buffered, the DLT remains 14 because the critical branch still passes
through SA1. The algorithm chooses SA1, which offers the maximum reduction weighted by the
strategic score. After this addition, the FG's DLT becomes 7 days, below the 12-day CTT,
and the algorithm stops.

The final result is a set of four decoupling points: MP1, C1, C3, SA1. Notice how the
structure is consistent with the theory: buffers have been placed at the nodes that break
the longest branches of the BOM, maximizing protection with the minimum number of buffered
items.

5. Buffer Zone Sizing (Top of Red / Yellow / Green)
Once the decoupling points are identified, the code moves on to zone sizing via the
buffer_zones function. For each buffered item, its individual DLT is computed and the
standard DDMRP formulas are applied. The Yellow Zone equals ADU × DLT, where ADU is the
Average Daily Usage. A crucial point is that the ADU is not simply the finished good's
demand — it is computed by the total_usage() function, which propagates demand along all
BOM paths by multiplying by the BOM quantities.

The Red Zone is calculated as ADU × DLT × Lead Time Factor × (1 + Variability Factor).
The Lead Time Factor is 0.7 for short DLT (< 8 days), 0.5 for medium (8-20 days), and 0.3
for long (> 20 days). The Green Zone represents the minimum order quantity and equals the
maximum between ADU × DLT × Lead Time Factor and the supplier's Minimum Order Quantity.

The three values TOR (Top of Red), TOY (Top of Yellow), and TOG (Top of Green) define the
operational thresholds: when the Net Flow Position drops below TOY, a replenishment order
is triggered; when it drops below TOR, a maximum-priority red alert is raised. In this way,
the system transforms the strategic positioning into a day-to-day operational logic, closing
the loop between DDMRP theory and shop-floor execution.
"""

from __future__ import annotations
from dataclasses import dataclass

# —————————————————————————
# 1) DATA MODEL: item and bill of materials
# —————————————————————————

@dataclass
class Item:
    code: str
    lt: float                  # individual lead time (days)
    source: str                # "make" or "buy"
    demand_var: float = 0.0    # demand variability 0..1
    supply_var: float = 0.0    # supply variability 0..1
    allow_buffer: bool = True  # can we place a buffer here?
    buffered: bool = False     # is it a decoupling point? (result)

# BOM: parent -> list of (child, quantity)
BOM: dict[str, list[tuple[str, float]]] = {}
ITEMS: dict[str, Item] = {}

def add_item(item: Item) -> None:
    ITEMS[item.code] = item
    BOM.setdefault(item.code, [])

def add_link(parent: str, child: str, qty: float) -> None:
    BOM.setdefault(parent, []).append((child, qty))

# —————————————————————————
# 2) STRUCTURE HELPERS
# —————————————————————————

def children(code: str) -> list[tuple[str, float]]:
    return BOM.get(code, [])

def parents_count(code: str) -> int:
    """Number of distinct parents (commonality index)."""
    return sum(1 for p, links in BOM.items() for (ch, _) in links if ch == code)

def root_item() -> str:
    """The finished good: the only item without parents."""
    child_codes = {ch for links in BOM.values() for (ch, _) in links}
    roots = [c for c in ITEMS if c not in child_codes]
    if not roots:
        raise ValueError("BOM is empty or has no root.")
    return roots[0]

def topological_order() -> list[str]:
    """Topological ordering (Kahn's algorithm): parents before children."""
    indeg = {c: 0 for c in ITEMS}
    for links in BOM.values():
        for (ch, _) in links:
            indeg[ch] += 1
    queue = [c for c in ITEMS if indeg[c] == 0]
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for (ch, _) in children(n):
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
    if len(order) != len(ITEMS):
        raise ValueError("Cycle detected in the BOM.")
    return order

def has_buffered_ancestor(code: str, visited: set[str] | None = None) -> bool:
    """True if at least one ancestor is already a decoupling point."""
    if visited is None:
        visited = set()
    if code in visited:  # protection against unexpected cycles
        return False
    visited.add(code)
    for p, links in BOM.items():
        for (ch, _) in links:
            if ch == code:
                if ITEMS[p].buffered or has_buffered_ancestor(p, visited):
                    return True
    return False

# —————————————————————————
# 3) LEAD TIME: cumulative vs decoupled (DLT)
# —————————————————————————

def decoupled_lt(code: str, respect_buffers: bool = True) -> float:
    """
    Lead time of the longest chain below 'code'. If respect_buffers is True,
    a buffered child is available from stock and contributes 0
    (breaks the chain). With respect_buffers=False we obtain the classic
    cumulative lead time (without buffers).
    """
    kids = children(code)
    if not kids:
        return ITEMS[code].lt
    max_contrib = 0.0
    for (ch, _) in kids:
        if respect_buffers and ITEMS[ch].buffered:
            contrib = 0.0                      # stocked child: chain is broken
        else:
            contrib = decoupled_lt(ch, respect_buffers)
        max_contrib = max(max_contrib, contrib)
    return ITEMS[code].lt + max_contrib

# —————————————————————————
# 4) DEMAND PROPAGATION (ADU per item)
# —————————————————————————

def total_usage() -> dict[str, float]:
    """
    Total quantity of each item per unit of finished good,
    summing over all paths (handles common components).
    """
    usage = {c: 0.0 for c in ITEMS}
    usage[root_item()] = 1.0
    for node in topological_order():            # parents before children
        for (ch, qty) in children(node):
            usage[ch] += usage[node] * qty
    return usage

# —————————————————————————
# 5) STRATEGIC SCORE OF A CANDIDATE
# —————————————————————————

def strategic_score(code: str, max_lt: float, max_par: int) -> float:
    it = ITEMS[code]
    s_lt = it.lt / max_lt if max_lt else 0.0
    s_common = parents_count(code) / max_par if max_par else 0.0
    s_var = max(it.demand_var, it.supply_var)
    s_buy = 1.0 if it.source == "buy" else 0.5
    return 0.35 * s_lt + 0.30 * s_common + 0.25 * s_var + 0.10 * s_buy

# —————————————————————————
# 6) POSITIONING ALGORITHM
# —————————————————————————

def position_decoupling_points(ctt: float) -> list[dict]:
    """
    Selects the decoupling points and returns the list with the reasons.
    """
    root = root_item()
    max_lt = max(i.lt for i in ITEMS.values())
    max_par = max((parents_count(c) for c in ITEMS), default=1)
    selected: list[dict] = []

    # --- PHASE 1: protection of purchased items ----------------------------
    buy_candidates = [c for c, it in ITEMS.items()
                      if it.source == "buy" and it.allow_buffer]
    # Sort by decreasing cumulative lead time (more consistent with DDMRP)
    buy_candidates.sort(key=lambda c: decoupled_lt(c, respect_buffers=False), reverse=True)

    for c in buy_candidates:
        it = ITEMS[c]
        lt_cum = decoupled_lt(c, respect_buffers=False)
        # Buffer if cumulative lead time exceeds CTT or supply variability is critical
        if (lt_cum > ctt) or it.supply_var >= 0.5:
            if not has_buffered_ancestor(c):
                it.buffered = True
                selected.append({
                    "code": c,
                    "phase": "protection",
                    "reason": f"purchased, cumulative LT {lt_cum:.1f}d > CTT {ctt:.1f}d or high var.",
                    "score": round(strategic_score(c, max_lt, max_par), 3),
                })

    # --- PHASE 2: compression until CTT is met -----------------------------
    while decoupled_lt(root) > ctt:
        best = None
        best_val = 0.0
        base = decoupled_lt(root)
        for c, it in ITEMS.items():
            if it.buffered or not it.allow_buffer or c == root:
                continue
            it.buffered = True                  # temporary trial
            reduction = base - decoupled_lt(root)
            it.buffered = False                 # restore
            if reduction <= 0:
                continue
            # balance compression and strategic score
            val = reduction * (0.5 + strategic_score(c, max_lt, max_par))
            if val > best_val:
                best_val, best = val, c
        if best is None:
            break                               # impossible to meet CTT
        ITEMS[best].buffered = True
        it = ITEMS[best]
        selected.append({
            "code": best,
            "phase": "compression",
            "reason": f"reduces FG DLT on the longest branch (reduction: {base - decoupled_lt(root):.1f}d)",
            "score": round(strategic_score(best, max_lt, max_par), 3),
        })
    return selected

# —————————————————————————
# 7) BUFFER ZONE SIZING
# —————————————————————————

def lead_time_factor(dlt: float) -> float:
    if dlt >= 20: return 0.3      # long
    if dlt >= 8:  return 0.5      # medium
    return 0.7                    # short

def variability_factor(v: float) -> float:
    if v >= 0.5: return 0.6       # high
    if v >= 0.3: return 0.45      # medium
    return 0.25                   # low

@dataclass
class Zones:
    red: float
    yellow: float
    green: float
    @property
    def tor(self) -> float: return self.red
    @property
    def toy(self) -> float: return self.red + self.yellow
    @property
    def tog(self) -> float: return self.red + self.yellow + self.green

def buffer_zones(code: str, adu: float, moq: float = 0.0) -> Zones:
    it = ITEMS[code]
    dlt = decoupled_lt(code)                    # DLT of the point itself
    ltf = lead_time_factor(dlt)
    vf = variability_factor(max(it.demand_var, it.supply_var))
    yellow = adu * dlt
    red_base = yellow * ltf
    red = red_base + red_base * vf
    green = max(yellow * ltf, moq)
    return Zones(red=red, yellow=yellow, green=green)

# —————————————————————————
# 8) FULL DEMO
# —————————————————————————

def build_bom() -> None:
    """4-level BOM with a common component (C1) and two long-purchased items."""
    add_item(Item("PF",  lt=3,  source="make", demand_var=0.4, supply_var=0.1,
                  allow_buffer=False))          # finished good: make-to-order
    add_item(Item("SA1", lt=5,  source="make", demand_var=0.3, supply_var=0.2))
    add_item(Item("SA2", lt=7,  source="make", demand_var=0.3, supply_var=0.2))
    add_item(Item("C1",  lt=8,  source="buy",  demand_var=0.3, supply_var=0.5))
    add_item(Item("C2",  lt=6,  source="buy",  demand_var=0.2, supply_var=0.3))
    add_item(Item("C3",  lt=20, source="buy",  demand_var=0.4, supply_var=0.6))
    add_item(Item("MP1", lt=15, source="buy",  demand_var=0.2, supply_var=0.7))

    add_link("PF", "SA1", 1); add_link("PF", "SA2", 2)
    add_link("SA1", "C1", 2); add_link("SA1", "C2", 1)
    add_link("SA2", "C1", 1); add_link("SA2", "C3", 3)
    add_link("C1", "MP1", 1)

if __name__ == "__main__":
    build_bom()
    root = root_item()
    CTT = 12.0          # customer tolerance time (days)
    FG_ADU = 20.0       # finished good demand (units/day)

    cumulative = decoupled_lt(root, respect_buffers=False)
    print("=== BOM AND LEAD TIMES ===")
    print(f"Finished good: {root}")
    print(f"CUMULATIVE lead time (no buffers): {cumulative:.1f} days")
    print(f"Customer CTT: {CTT} days\n")

    # 1) Positioning
    print("=== DECOUPLING POINTS POSITIONING ===")
    points = position_decoupling_points(CTT)
    for p in points:
        print(f"- {p['code']:<4} | Phase: {p['phase']:<12} | Score: {p['score']} | {p['reason']}")

    # 2) Zone sizing (with real ADU per component)
    usages = total_usage()
    print("\n=== BUFFER ZONE SIZING ===")
    print(f"{'Code':<6} {'Real ADU':>10} {'DLT':>6} {'Red':>8} {'Yellow':>8} {'Green':>8} {'TOG':>8}")
    print("-" * 68)
    for p in points:
        code = p['code']
        real_adu = FG_ADU * usages[code]  # multiply FG demand by BOM usage
        dlt = decoupled_lt(code)
        z = buffer_zones(code, adu=real_adu, moq=50.0)
        print(f"{code:<6} {real_adu:>10.1f} {dlt:>6.1f} {z.red:>8.1f} {z.yellow:>8.1f} {z.green:>8.1f} {z.tog:>8.1f}")