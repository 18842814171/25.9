## 1️⃣ inputs 
* **JSON1**: entities (circles, lines, text) — *geometry*
* **JSON2**: dimensions with defpoints — *intent*

But the missing piece is **dimension interpretation**.

## 2️⃣ Why dimensions do NOT auto-fix

A `DIMENSION` entity does **NOT** tell directly:

* Which circles it refers to
* Which rows or columns it constrains
* Whether it is horizontal or vertical in intent
* Whether it is row-to-row, column-to-column, or boundary-to-row

**Interpretation is mandatory.**

---

## 3️⃣ The missing layer: Dimension Resolver

We need a **Dimension Resolver** layer.

### Conceptually:

```
JSON geometry
JSON dimensions
      ↓
Dimension Resolver  ←── helper functions
      ↓
Resolved constraints
      ↓
2D Logical Knowledge Graph
      ↓
Constraint solver / fixer
```

---

## 4️⃣ What helper functions are REQUIRED (not optional)
---

### 🧩 Helper 1 — Dimension orientation

```python
def dimension_orientation(dim):
    # horizontal or vertical?
```

Use:

* `dimtype`
* defpoint2 vs defpoint3 delta

Result:

```python
"horizontal" or "vertical"
```

---

### 🧩 Helper 2 — Dimension span (projection)

> What line or band does this dimension refer to?

```python
def dimension_span(dim):
    # returns a projected line segment
```

For a vertical dimension:

* X is fixed
* Y spans between defpoints

For a horizontal dimension:

* Y is fixed
* X spans

---

### 🧩 Helper 3 — Snap dimension to rows or columns

This is the **most important helper**.

```python
def snap_dimension_to_rows(dim, row_nodes):
    # returns (row_a, row_b)
```

Logic:

* Project dimension endpoints
* Find nearest row centerlines
* Validate tolerance

---

### 🧩 Helper 4 — Boundary-aware snapping

Dimensions often measure:

* boundary → row
* boundary → column

```python
def snap_dimension_to_boundary(dim, boundary):
```

This explains:

* overall width (4200)
* overall height (2900)

---

### 🧩 Helper 5 — Conflict detection

```python
def validate_dimension(dim, graph):
    # check inconsistent or redundant constraints
```

E.g.:

* two dimensions claim different spacing between same rows

---

## 5️⃣ After helpers: building the graph (now it works)

Once helpers resolve dimensions, **graph building is trivial**.

Example resolved dimension:

```json
{
  "type": "dimension",
  "orientation": "vertical",
  "value": 500,
  "from": "Row_3",
  "to": "Row_4"
}
```

Graph edge:

```
(Row_3) ──[distance=500]──▶ (Row_4)
```

Now the graph **knows intent**.

---

### What must still be coded:

✔ How to move circles
✔ Which constraint has priority
✔ Whether to preserve boundary or interior spacing

---

## 7️⃣ Correct architecture 

```
[ JSON1: geometry ]
[ JSON2: dimensions ]
          ↓
  Dimension Resolver
    - orientation
    - snapping
    - validation
          ↓
  2D Logical Knowledge Graph
          ↓
  Constraint Solver
          ↓
  Geometry Correction
```
