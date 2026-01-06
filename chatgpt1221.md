1️⃣ What the drawing REALLY shows (no ambiguity)

In the middle area of the top view:

You have distinct vertical columns, each column containing exactly 2 circles in most cases.

Visually and semantically:

Column A: circles 1, 2, 3

Column B: circles 4, 5, 6

Column C: circles 7, 8

Column D: circles 9, 10

Column E: circles 22，21，19，38

Column F: circles 40，23，24，25，26，39

etc.

These are not accidental:

They are drilling columns

Each column is dimensioned (500, 400, etc.)

Dimensions are drawn between column centerlines

2️⃣ Why the current vertical grouping is still wrong

 vertical grouping logic is still this at heart:

cluster_1d(circles, axis="x", tol=3.0)

Even with the orthogonal Y-gap check, this still groups by:

“same X ≈ same column”

But in this drawing:

🔴 Columns are NOT defined by identical X

They are defined by:

column bands

separated by dimensioned spacing

sometimes with small X jitter

sometimes with leaders shifting circle centers slightly

So pure X-alignment is insufficient.

3️⃣ What actually defines a vertical group in THIS drawing

From the picture, a vertical group is:

A set of circles that:

Are roughly aligned in X

Are close in Y AND

Have no other circle between them in X

This is a topological column, not a numeric one.

4️⃣ The missing rule
prevent a vertical group from spanning multiple horizontal rows

Right now, nothing stops this:

circle at (x≈2400, y≈1200)
circle at (x≈2400, y≈1700)
circle at (x≈2400, y≈2100)


But visually, those belong to different column stacks, not one.

5️⃣ Probable fix

use computed horizontal groups (rows)to constrain vertical grouping.

Rule:

A vertical group may only contain circles from adjacent horizontal rows

6️⃣ Probable code change
Step 1 — build a lookup from circle → horizontal group

* already have this in circle_index.

Step 2 — modify vertical grouping

Replace vertical grouping call with this logic:
```python
def split_vertical_groups_by_rows(v_groups, circle_index, max_rows=2):
    new_groups = []

    for g in v_groups:
        # group circles by horizontal row
        row_buckets = {}
        for p in g:
            cid = p["circle_id"]
            row = circle_index[cid]["horizontal"]
            row_buckets.setdefault(row, []).append(p)

        # merge only adjacent rows, limited depth
        sorted_rows = sorted(row_buckets.items())
        current = []
        last_row = None

        for row, pts in sorted_rows:
            if last_row is None or row == last_row + 1:
                current.extend(pts)
            else:
                new_groups.append(current)
                current = pts[:]
            last_row = row

            if len(set(circle_index[p["circle_id"]]["horizontal"] for p in current)) > max_rows:
                new_groups.append(current[:-len(pts)])
                current = pts[:]

        if current:
            new_groups.append(current)

    return new_groups
```

Then apply it:

v_groups_raw = cluster_1d(circles, "x", tol=3.0)
v_groups = split_vertical_groups_by_rows(v_groups_raw, result["circle_index"])


8️⃣ Why this is the correct interpretation (engineering-wise)

Dimensions are between column centerlines

Rows and columns form a grid

A column is local, not global

CAD drafters expect column logic, not infinite X-lines

You are reading the drawing correctly.

✅ Final verdict

❌ Earlier “same X = same column” is wrong for this drawing

✅ Your interpretation of the picture is correct

✅ The fix is to bind vertical groups to horizontal structure