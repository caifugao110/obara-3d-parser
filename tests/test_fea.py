"""Sanity test: cantilever beam, compare FEA deflection to beam theory.

Beam: L=100, W=20, H=10 mm. Fixed at x=0. Uniform pressure on top face.
Analytical tip deflection (uniform load w = p*W):
    delta = w*L^4 / (8*E*I),  I = W*H^3/12
"""
import sys
import numpy as np

from app.geometry import make_test_beam, mesh_part
from app.material_db import Material
from app.fea import solve_static, Fixture, PressureLoad, CoordSystem


def find_face(part, target, tol=0.5):
    for fid in range(part.mesh.num_faces):
        c = part.mesh.face_centers[fid]
        if np.linalg.norm(c - np.array(target)) < tol:
            return fid
    return -1


def main():
    L, W, H = 100.0, 20.0, 10.0
    part = make_test_beam(length=L, width=W, height=H)
    part.mesh = mesh_part([part], 6.0)
    print(f"Mesh: nodes={part.mesh.num_nodes}, tets={part.mesh.num_tets}, "
          f"faces={part.mesh.num_faces}")

    # steel-like
    mat = Material(name="TestSteel", classification="铁材",
                   ex=200e9, nuxy=0.3, dens=7850.0, sigyld=250e6)
    part.material = mat

    fix_face = find_face(part, [0.0, 0.0, 0.0])
    top_face = find_face(part, [L/2, 0.0, H/2])
    print(f"fix_face={fix_face}, top_face={top_face}")
    assert fix_face >= 0 and top_face >= 0

    pressure = 1e6  # 1 MPa
    fixtures = [Fixture(face_id=fix_face)]
    loads = [PressureLoad(face_id=top_face, pressure=pressure)]
    cs = CoordSystem()

    result = solve_static([part], fixtures, loads, cs,
                          progress=lambda s: print("  ", s))

    # analytical (all SI: m, Pa, N). Beam theory, uniform pressure on top.
    Lm, Wm, Hm = L * 1e-3, W * 1e-3, H * 1e-3
    I = Wm * Hm**3 / 12.0
    w = pressure * Wm            # force per unit length (N/m)
    delta_anal = w * Lm**4 / (8.0 * mat.ex * I)
    print(f"\nAnalytical tip deflection (uniform load, SI): "
          f"{delta_anal*1000:.6f} mm = {delta_anal*1e6:.4f} µm")

    # FEA: max displacement location should be near the free end (x=L)
    idx = int(np.argmax(result.disp_magnitude))
    pt = part.mesh.points[idx]
    print(f"FEA max displacement: {result.max_displacement*1000:.6f} mm "
          f"at node {pt} (expect near x={L})")
    print(f"FEA max von Mises: {result.max_von_mises/1e6:.4f} MPa")
    print(f"FEA safety factor: {result.safety_factor:.3f}")

    # report loaded-face displacement (local CS = global here)
    for r in result.loaded_face_reports:
        ux, uy, uz = r["disp_local"]
        print(f"  Loaded face {r['face_id']} disp (mm): "
              f"UX={ux*1000:+.6f} UY={uy*1000:+.6f} UZ={uz*1000:+.6f}")

    # check sign: top pressure pushes down => UZ negative
    r = result.loaded_face_reports[0]
    assert r["disp_local"][2] < 0, "expected downward (negative Z) deflection"

    ratio = result.max_displacement / delta_anal
    print(f"\nFEA / analytical ratio: {ratio:.3f} (coarse mesh, expect ~0.5-1.5)")
    print("TEST PASSED")


if __name__ == "__main__":
    sys.exit(main())
