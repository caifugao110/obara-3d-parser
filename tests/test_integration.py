"""Headless integration test: exercise the code paths the GUI uses.

Validates viewport PolyData construction, study workflow, load editing and
results formatting without rendering Qt windows.
"""
import numpy as np
import pyvista as pv

from app.geometry import make_test_beam, mesh_part
from app.material_db import load_material_database, find_material
from app.study import Study
from app.fea import solve_static, Fixture, PressureLoad, ForceLoad, CoordSystem
from app.viewport import _surface_polydata, _face_submesh


def main():
    db_path = "material_data/sldmaterials.json"
    mats = load_material_database(db_path)
    print(f"Loaded {len(mats)} materials across "
          f"{len(set(m.classification for m in mats))} classifications")

    # pick a real steel from the DB
    steel = find_material(mats, "1060") or find_material(mats, "AISI 1020") or mats[0]
    print(f"Using material: {steel.name} ({steel.classification}), "
          f"E={steel.ex/1e9:.1f} GPa, nu={steel.nuxy}, "
          f"SIGYLD={steel.sigyld/1e6:.1f} MPa")

    # build part + viewport polydata (same path the viewport uses)
    part = make_test_beam(100.0, 20.0, 10.0)
    part.mesh = mesh_part([part], 5.0)
    surf = _surface_polydata(part)
    sub = _face_submesh(part, 0)
    print(f"Surface polydata: {surf.n_points} pts, {surf.n_cells} tris; "
          f"face0 submesh: {sub.n_points} pts")
    assert surf.n_cells == len(part.mesh.surf_tris)

    # build study (same path the GUI's MainWindow uses)
    part.material = steel
    study = Study(name="integration", parts=[part])
    # fix face at x=0
    fix_face = next(i for i in range(part.mesh.num_faces)
                    if abs(part.mesh.face_centers[i][0]) < 0.5)
    study.fixtures.append(Fixture(face_id=fix_face))
    # pressure on top face
    top_face = next(i for i in range(part.mesh.num_faces)
                    if abs(part.mesh.face_centers[i][0] - 50) < 0.5
                    and abs(part.mesh.face_centers[i][2] - 5) < 0.5)
    study.loads.append(PressureLoad(face_id=top_face, pressure=2e6, name="top load"))

    assert study.is_ready(), study.ready_report()

    # use a rotated coordinate system (45deg about Z)
    c = np.cos(np.pi / 4); s = np.sin(np.pi / 4)
    study.coord_system = CoordSystem(
        origin=np.array([50.0, 0.0, 0.0]),
        x_axis=np.array([c, s, 0.0]),
        y_axis=np.array([-s, c, 0.0]),
    )

    result = solve_static(
        study.parts, study.fixtures, study.loads,
        study.coord_system, progress=lambda m: None,
    )
    study.result = result

    print(f"\nResult: max_disp={result.max_displacement*1000:.5f} mm, "
          f"max_vm={result.max_von_mises/1e6:.3f} MPa, "
          f"safety={result.safety_factor:.3f}")
    assert result.max_displacement > 0
    assert result.max_von_mises > 0
    assert result.safety_factor > 0

    print("Loaded-face report (local CS):")
    for r in result.loaded_face_reports:
        ux, uy, uz = r["disp_local"]
        print(f"  {r['name']}: UX={ux*1000:+.5f} UY={uy*1000:+.5f} "
              f"UZ={uz*1000:+.5f} mm (mag {r['magnitude']*1000:.5f} mm)")

    # verify local-CS rotation: magnitude preserved
    for r in result.loaded_face_reports:
        g = np.array(r["disp_global"])
        l = np.array(r["disp_local"])
        assert abs(np.linalg.norm(g) - np.linalg.norm(l)) < 1e-9, "rotation must preserve magnitude"

    # test removing a load updates readiness
    study.loads.clear()
    assert not study.is_ready()
    print("\nReadiness toggles correctly after clearing loads.")

    print("\nALL INTEGRATION CHECKS PASSED")


if __name__ == "__main__":
    main()
