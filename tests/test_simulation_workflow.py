import numpy as np

from app.fea import CoordSystem, Fixture, PressureLoad
from app.geometry import make_test_beam, mesh_part
from app.material_db import find_material, load_material_database
from app.solver_backends import solve_study
from app.study import Study
from app.viewport import _cad_edge_polydata, _surface_polydata


def _find_face(part, predicate):
    for face_id, center in enumerate(part.mesh.face_centers):
        if predicate(center):
            return face_id
    raise AssertionError("expected face was not found")


def test_internal_static_simulation_workflow():
    part = make_test_beam(length=100.0, width=20.0, height=10.0)
    study = Study(name="pytest workflow", parts=[part], mesh_size=6.0)

    assert not study.is_ready()
    assert "尚未定义材质" in "；".join(study.ready_report())

    part.mesh = mesh_part(study.parts, study.mesh_size)
    surface = _surface_polydata(part)
    cad_edges = _cad_edge_polydata(part)
    assert surface.n_cells == len(part.mesh.surf_tris)
    assert cad_edges.n_cells > 0
    assert cad_edges.n_verts == 0

    materials = load_material_database("material_data/sldmaterials.json")
    part.material = find_material(materials, "1060") or materials[0]

    fixed_face = _find_face(part, lambda center: abs(center[0]) < 0.5)
    loaded_face = _find_face(
        part,
        lambda center: abs(center[0] - 50.0) < 0.5 and abs(center[2] - 5.0) < 0.5,
    )
    study.fixtures.append(Fixture(face_id=fixed_face))
    study.loads.append(PressureLoad(face_id=loaded_face, pressure=1.0e6, name="top pressure"))

    angle = np.pi / 6.0
    study.coord_system = CoordSystem(
        origin=np.array([50.0, 0.0, 0.0]),
        x_axis=np.array([np.cos(angle), np.sin(angle), 0.0]),
        y_axis=np.array([-np.sin(angle), np.cos(angle), 0.0]),
    )
    assert study.is_ready(), study.ready_report()

    result = solve_study(
        study.solver_backend,
        study.parts,
        study.fixtures,
        study.loads,
        study.coord_system,
        progress=lambda _: None,
    )
    study.result = result

    assert result.num_nodes == part.mesh.num_nodes
    assert result.num_tets == part.mesh.num_tets
    assert result.displacements.shape == (part.mesh.num_nodes, 3)
    assert result.max_displacement > 0
    assert result.max_von_mises > 0
    assert result.safety_factor > 0
    assert result.loaded_face_reports[0]["face_id"] == loaded_face

    probe_node = int(np.argmax(result.disp_magnitude))
    probe_payload = {
        "point_id": probe_node,
        "coords": part.mesh.points[probe_node].tolist(),
        "ux": float(result.displacements[probe_node, 0] * 1000.0),
        "uy": float(result.displacements[probe_node, 1] * 1000.0),
        "uz": float(result.displacements[probe_node, 2] * 1000.0),
        "disp_magnitude": float(result.disp_magnitude[probe_node] * 1000.0),
        "von_mises": float(result.von_mises[probe_node] / 1.0e6),
    }
    assert probe_payload["disp_magnitude"] > 0
    assert len(probe_payload["coords"]) == 3
