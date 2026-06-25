# ddmrp-decoupling-points
DDMRP decoupling point positioning algorithm — interactive BOM visualization
# Presentation Notes — DDMRP Algorithm for Decoupling Point Positioning

---

## 1. Introduction to DDMRP

**Demand Driven Material Requirements Planning (DDMRP)** is a supply chain planning and control methodology developed in 2011 by *Ptak and Smith* as a critical evolution of traditional MRP/ERP systems. The core problem DDMRP aims to solve is the so-called **bullwhip effect**: in a classical MRP system, a small fluctuation in final demand progressively amplifies upstream through the bill of materials, causing oversized inventory, stockouts, and perceived lead times that are far too long.

DDMRP departs from the *push* logic of MRP (which "pushes" orders based on forecasts) by introducing five operational components:

- **Strategic buffer positioning** (the focus of our code)
- **Buffer zone sizing** (Red / Yellow / Green)
- **Dynamic adjustments**
- **Demand-driven planning**
- **Visible and collaborative execution**

The conceptual core is simple: instead of planning everything from the finished good, **decoupling points** are deliberately inserted along the bill of materials — nodes where the supply chain is "broken" by a stock buffer. Upstream of the buffer, the system operates in *push* logic (to replenish stock); downstream, it operates in *pull* logic (to satisfy real demand). In this way, uncertainty no longer propagates in a cascading fashion, but is absorbed locally.

---

## 2. Decoupling Points

A **decoupling point** is a BOM item to which an actively managed stock buffer is assigned. Its function is twofold:

1. It **protects downstream levels** from supply or production uncertainties (lead time variability, quality issues, supplier reliability).
2. It **compresses the cumulative lead time perceived by the customer**, because when an order arrives, it is no longer necessary to wait for the entire supply chain — only for the segment from the nearest decoupling point to the finished good.

The choice of *where* to position these points is not arbitrary:

- Buffering **too many items** ties up capital and increases carrying costs.
- Buffering **too few items** exposes the company to stockouts and unacceptable lead times.

DDMRP provides a structured methodology based on **six strategic factors**:

- **Customer Tolerance Time (CTT)** — how long the customer is willing to wait.
- **External variability** of demand and supply.
- **Component commonality** — a component used by many parents deserves a buffer because it protects multiple flows simultaneously.
- **Protection of critical operations**.
- **Lead time compression** toward the finished good.

---

## 3. The Positioning Algorithm: Two Phases

The code implements a **two-phase algorithm** that operationalizes the DDMRP principles.

### Phase 1 — Protection
Identifies purchased items whose **cumulative lead time** — computed as the longest chain connecting them to raw materials — exceeds the customer's CTT, or that exhibit high supply variability. These items represent a structural risk: if not buffered, every customer order would have to wait for the entire procurement cycle.

### Phase 2 — Compression
Intervenes only if, after Phase 1, the **Decoupled Lead Time (DLT)** of the finished good remains above the CTT. In this case, the algorithm iteratively searches for the best item to buffer, evaluating for each candidate both:

- The **effective reduction** in the finished good's DLT.
- A **strategic score** combining individual lead time, commonality, variability, and the item's nature.

The iteration stops as soon as the finished good's DLT drops below the CTT, or when no useful candidates remain.

---

## 4. How the Code Works: A Numerical Example

To understand the concrete behavior, consider the demo BOM, which represents a finished good (**FG**) assembled from two sub-assemblies (**SA1**, **SA2**), which in turn use purchased components (**C1**, **C2**, **C3**) and a raw material (**MP1**). The customer CTT is set to **12 days**.

### Step 1 — Cumulative Lead Times
The first step is computing the cumulative lead time of each item, i.e., the sum of lead times along the longest branch of the BOM ending at that item:

| Item | Cumulative LT (days) | Calculation |
|------|---------------------|-------------|
| MP1  | 15                  | 15 (only its own LT) |
| C1   | 23                  | 8 + 15 (MP1) |
| C3   | 20                  | 20 (only its own LT) |
| SA1  | 28                  | 5 + 23 (C1, the longest branch between C1 and C2) |
| SA2  | 30                  | 7 + 23 (C1) |
| FG   | 33                  | 3 + 30 (SA2) |

Since 33 ≫ 12, it is clear that without buffers the customer would have to wait more than a month.

### Step 2 — Phase 1 (Protection)
The code selects all items with `source="buy"` and computes their cumulative LT:

- **MP1** (15 > 12) → buffered
- **C3** (20 > 12) → buffered
- **C1** (23 > 12) → buffered
- **C2** (cumulative LT = 6, low supply variability = 0.3) → **skipped**

The `has_buffered_ancestor` function prevents redundant buffering when an upstream buffer already protects the item and supply variability is not critical — avoiding unnecessary capital lock-up.

### Step 3 — Recomputing the Finished Good DLT
At the end of Phase 1, the code recomputes the FG's DLT using `decoupled_lt(root, respect_buffers=True)`. This function traverses the BOM depth-first and, every time it encounters a buffered child, stops counting lead time (because that component is already available from stock):

- **SA1** contributes 11 days (5 + 6 from C2, since C1 is now buffered and contributes 0).
- **SA2** contributes 7 days (both C1 and C3 are buffered).
- **FG** contributes 3 + max(11, 7) = **14 days**.

Since 14 > 12, **Phase 2 is triggered**.

### Step 4 — Phase 2 (Compression)
Phase 2 heuristically tests each non-buffered candidate:

- Buffering **SA1** → FG DLT drops from 14 to **7** (reduction of 7 days).
- Buffering **C2** → FG DLT drops to **10** (reduction of 4 days).
- Buffering **SA2** → FG DLT stays at 14 (the critical branch still passes through SA1).

The algorithm chooses **SA1**, which offers the maximum reduction weighted by the strategic score. After this addition, the FG's DLT becomes **7 days**, below the 12-day CTT, and the algorithm stops.

### Final Result
The final set of decoupling points is: **MP1, C1, C3, SA1**. Notice how the structure is consistent with the theory: buffers have been placed at the nodes that break the longest branches of the BOM, maximizing protection with the minimum number of buffered items.

---

## 5. Buffer Zone Sizing (Top of Red / Yellow / Green)

Once the decoupling points are identified, the code moves on to **zone sizing** via the `buffer_zones` function. For each buffered item, its individual DLT is computed (the lead time of the longest chain starting from that item, stopping at its buffered children), and the standard DDMRP formulas are applied.

### Yellow Zone (Yellow Order Zone)

$$
\text{Yellow} = \text{ADU} \times \text{DLT}
$$

where **ADU** (*Average Daily Usage*) is the item's average daily requirement. A crucial point in the code is that the ADU is **not** simply the finished good's demand — it is computed by the `total_usage()` function, which propagates demand along all BOM paths by multiplying by the BOM quantities. Thus, a component used in 2 copies per finished good will have an ADU **double** that of the finished good.

### Red Zone (Red Safety Zone)

$$
\text{Red} = \text{ADU} \times \text{DLT} \times \text{Lead Time Factor} \times (1 + \text{Variability Factor})
$$

The **Lead Time Factor** is:

- **0.7** for short DLT (< 8 days)
- **0.5** for medium DLT (8–20 days)
- **0.3** for long DLT (> 20 days)

Paradoxically, the longer the lead time, the smaller the additional safety fraction — because the yellow zone is already large on its own. The **Variability Factor** adds a further margin proportional to the combined uncertainty of demand and supply.

### Green Zone (Green Order Zone)

$$
\text{Green} = \max(\text{ADU} \times \text{DLT} \times \text{Lead Time Factor},\; \text{MOQ})
$$

where **MOQ** is the supplier's Minimum Order Quantity.

### Operational Thresholds

The three values **TOR** (Top of Red), **TOY** (Top of Yellow), and **TOG** (Top of Green) define the operational thresholds:

- When the **Net Flow Position** (available stock minus open orders) drops below **TOY** → a replenishment order is triggered.
- When it drops below **TOR** → a maximum-priority red alert is raised.

In this way, the system transforms the strategic positioning into a day-to-day operational logic, closing the loop between DDMRP theory and shop-floor execution.

To view the HTML content, please visit: [DDMRP Decoupling Points Presentation](https://danieledellamora1971-ops.github.io/ddmrp-decoupling-points/ddmrp_presentation_en.html)
