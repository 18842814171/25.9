# Stage 4 semantic ontology

Mining-drawing intuition mapped to topology:

| Shape | Mining intuition | `region_semantic` | `detail_type` | Topology |
| ----- | ---------------- | ----------------- | ------------- | -------- |
| `=` between two corridors | passage connecting corridors | `AUXILIARY_CORRIDOR` | `auxiliary_corridor` | parallel stub pair with both legs long enough |
| `几` attached to one corridor | alcove / recess / niche | `NICHE` | `niche` | touch chain of three stubs with outer legs parallel |
| (other parallel to known wall) | possible missing corridor wall | `POSSIBLE_CORRIDOR_WALL` | `possible_corridor_wall` | corridor-stub-parallel to a determined wall |
| (other) | — | `UNCLASSIFIED` | `unknown` | none of the above |

**Classifier order:**

1. NICHE — touch chain stub1—stub2—stub3 with stub1 ∥ stub3
2. POSSIBLE_CORRIDOR_WALL — corridor-stub-parallel to known wall
3. AUXILIARY_CORRIDOR — parallel pair, both legs ≥ scale × pair width
4. UNCLASSIFIED

Long/short leg checks use `stub-stub-parallel` edge width when present, otherwise the global median corridor width.
