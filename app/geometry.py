"""Geometry / mesh handling.

Loads a STEP file (or generates a test part) through Gmsh's OpenCASCADE
kernel, meshes it into linear tetrahedra, and extracts the boundary
surface triangles grouped by their originating face entity. These face
groups are the selectable surfaces used to apply fixtures and loads, the
same workflow as SolidWorks Simulation.
"""
from __future__ import annotations

import gmsh
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class TetMesh:
    points: np.ndarray         # (N,3) float64  node coordinates
    tets: np.ndarray           # (M,4) int32     tet node indices (0-based)
    surf_tris: np.ndarray      # (K,3) int32     surface triangle node indices
    tri_to_face: np.ndarray    # (K,)  int32     face id for each surface triangle
    face_centers: np.ndarray   # (F,3) float64   centroid of each face
    face_areas: np.ndarray     # (F,)  float64   area of each face
    face_normals: np.ndarray   # (F,3) float64   unit normal of each face
    tet_to_part: np.ndarray    # (M,)  int32     part index for each tetrahedron
    tri_to_part: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int32))

    @property
    def num_nodes(self) -> int:
        return int(self.points.shape[0])

    @property
    def num_tets(self) -> int:
        return int(self.tets.shape[0])

    @property
    def num_faces(self) -> int:
        return int(self.face_centers.shape[0])

    def face_triangles(self, face_id: int) -> np.ndarray:
        return self.surf_tris[self.tri_to_face == face_id]
    
    def part_tets(self, part_idx: int) -> np.ndarray:
        return self.tets[self.tet_to_part == part_idx]


@dataclass
class Part:
    name: str
    mesh: Optional[TetMesh] = None
    source: str = ""
    _gmsh_model: Optional[str] = None
    _step_path: Optional[Path] = None
    _beam_params: Optional[dict] = None
    material: Optional['Material'] = None
    _entity_tag: Optional[int] = None


def _finalize_mesh(mesh_size: float, part_name: str) -> TetMesh:
    """Extract nodes/elements from the current Gmsh model into a TetMesh."""
    # --- nodes ---
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    node_tags = np.asarray(node_tags, dtype=np.int64)
    pts = np.asarray(node_coords, dtype=np.float64).reshape(-1, 3)
    # map gmsh 1-based tag -> 0-based contiguous index
    tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

    # --- tetrahedra (element type 4) ---
    tet_tags, tet_node_tags = gmsh.model.mesh.getElementsByType(4)
    tet_nodes = np.asarray(tet_node_tags, dtype=np.int64).reshape(-1, 4)
    tets = np.array([[tag_to_idx[int(n)] for n in row] for row in tet_nodes],
                    dtype=np.int32)

    # --- surface triangles, grouped by 2D entity (face) ---
    surf_entities = gmsh.model.getEntities(2)
    vol_entities = gmsh.model.getEntities(3)
    part_face_map: dict[int, int] = {}
    for part_idx, (dim, vol_tag) in enumerate(vol_entities):
        try:
            boundary = gmsh.model.getBoundary([(dim, vol_tag)], oriented=False, recursive=False)
        except Exception:
            continue
        for face_dim, face_tag in boundary:
            if face_dim == 2:
                part_face_map[int(face_tag)] = part_idx
    tri_list: List[np.ndarray] = []
    tri_face_list: List[int] = []
    tri_part_list: List[np.ndarray] = []
    face_centers: List[np.ndarray] = []
    face_areas: List[float] = []
    face_normals: List[np.ndarray] = []

    for face_id, (dim, tag) in enumerate(surf_entities):
        try:
            tri_tags_e, tri_node_tags_e = gmsh.model.mesh.getElementsByType(2, tag)
        except Exception:
            continue
        if len(tri_tags_e) == 0:
            continue
        tris_e = np.asarray(tri_node_tags_e, dtype=np.int64).reshape(-1, 3)
        tris_idx = np.array([[tag_to_idx[int(n)] for n in row] for row in tris_e],
                            dtype=np.int32)
        tri_list.append(tris_idx)
        tri_face_list.append(np.full(len(tris_idx), face_id, dtype=np.int32))
        tri_part_list.append(np.full(len(tris_idx), part_face_map.get(int(tag), 0), dtype=np.int32))

        # face centroid = mean of triangle centroids weighted by area
        p0 = pts[tris_idx[:, 0]]
        p1 = pts[tris_idx[:, 1]]
        p2 = pts[tris_idx[:, 2]]
        cross = np.cross(p1 - p0, p2 - p0)
        area = 0.5 * np.linalg.norm(cross, axis=1)
        tri_centroids = (p0 + p1 + p2) / 3.0
        total_area = float(area.sum())
        if total_area > 0:
            center = (tri_centroids * area[:, None]).sum(axis=0) / total_area
            # orient normal by majority sign using cross sum
            nrm = cross.sum(axis=0)
            nrm = nrm / (np.linalg.norm(nrm) + 1e-30)
        else:
            center = tri_centroids.mean(axis=0) if len(tri_centroids) else np.zeros(3)
            nrm = np.array([0.0, 0.0, 1.0])
        face_centers.append(center)
        face_areas.append(total_area)
        face_normals.append(nrm)

    if tri_list:
        surf_tris = np.vstack(tri_list)
        tri_to_face = np.concatenate(tri_face_list)
        tri_to_part = np.concatenate(tri_part_list)
    else:
        surf_tris = np.zeros((0, 3), dtype=np.int32)
        tri_to_face = np.zeros((0,), dtype=np.int32)
        tri_to_part = np.zeros((0,), dtype=np.int32)

    return TetMesh(
        points=pts,
        tets=tets,
        surf_tris=surf_tris,
        tri_to_face=tri_to_face,
        face_centers=np.array(face_centers, dtype=np.float64) if face_centers else np.zeros((0, 3)),
        face_areas=np.array(face_areas, dtype=np.float64) if face_areas else np.zeros((0,)),
        face_normals=np.array(face_normals, dtype=np.float64) if face_normals else np.zeros((0, 3)),
        tet_to_part=np.zeros(len(tets), dtype=np.int32),
        tri_to_part=tri_to_part,
    )


def load_step(path: str | Path, name: Optional[str] = None) -> list[Part]:
    """Import a STEP file and return a list of :class:`Part` objects.
    
    Generates a surface mesh for display and picking. The full tetrahedral
    mesh is deferred until :func:`mesh_part` is called during simulation.
    
    If the STEP file contains multiple 3D entities (parts), each is returned
    as a separate Part with its own entity tag.
    """
    path = Path(path)
    base_name = name or path.stem

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 1)  # Delaunay for speed
        gmsh.option.setNumber("Mesh.MeshSizeMin", 2.0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 6.0)
        gmsh.model.add(base_name)
        gmsh.merge(str(path))
        vol_entities = gmsh.model.getEntities(3)
        gmsh.model.mesh.generate(2)
        mesh = _finalize_mesh_for_display(base_name)

        if len(vol_entities) == 0:
            return [Part(name=base_name, mesh=mesh, source=str(path), _step_path=path)]

        parts = []
        for idx, (dim, tag) in enumerate(vol_entities):
            part_name = f"{base_name}_{idx+1}" if len(vol_entities) > 1 else base_name
            parts.append(
                Part(name=part_name, mesh=mesh, source=str(path),
                     _step_path=path, _entity_tag=tag)
            )

        return parts
    finally:
        gmsh.finalize()


def _finalize_mesh_for_display(part_name: str) -> TetMesh:
    """Extract surface mesh from the current Gmsh model for display/picking."""
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    node_tags = np.asarray(node_tags, dtype=np.int64)
    pts = np.asarray(node_coords, dtype=np.float64).reshape(-1, 3)
    tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}

    surf_entities = gmsh.model.getEntities(2)
    vol_entities = gmsh.model.getEntities(3)
    part_face_map: dict[int, int] = {}
    for part_idx, (dim, vol_tag) in enumerate(vol_entities):
        try:
            boundary = gmsh.model.getBoundary([(dim, vol_tag)], oriented=False, recursive=False)
        except Exception:
            continue
        for face_dim, face_tag in boundary:
            if face_dim == 2:
                part_face_map[int(face_tag)] = part_idx
    tri_list: List[np.ndarray] = []
    tri_face_list: List[int] = []
    tri_part_list: List[np.ndarray] = []
    face_centers: List[np.ndarray] = []
    face_areas: List[float] = []
    face_normals: List[np.ndarray] = []

    for face_id, (dim, tag) in enumerate(surf_entities):
        try:
            tri_tags_e, tri_node_tags_e = gmsh.model.mesh.getElementsByType(2, tag)
        except Exception:
            continue
        if len(tri_tags_e) == 0:
            continue
        tris_e = np.asarray(tri_node_tags_e, dtype=np.int64).reshape(-1, 3)
        tris_idx = np.array([[tag_to_idx[int(n)] for n in row] for row in tris_e],
                            dtype=np.int32)
        tri_list.append(tris_idx)
        tri_face_list.append(np.full(len(tris_idx), face_id, dtype=np.int32))
        tri_part_list.append(np.full(len(tris_idx), part_face_map.get(int(tag), 0), dtype=np.int32))

        p0 = pts[tris_idx[:, 0]]
        p1 = pts[tris_idx[:, 1]]
        p2 = pts[tris_idx[:, 2]]
        cross = np.cross(p1 - p0, p2 - p0)
        area = 0.5 * np.linalg.norm(cross, axis=1)
        tri_centroids = (p0 + p1 + p2) / 3.0
        total_area = float(area.sum())
        if total_area > 0:
            center = (tri_centroids * area[:, None]).sum(axis=0) / total_area
            nrm = cross.sum(axis=0)
            nrm = nrm / (np.linalg.norm(nrm) + 1e-30)
        else:
            center = tri_centroids.mean(axis=0) if len(tri_centroids) else np.zeros(3)
            nrm = np.array([0.0, 0.0, 1.0])
        face_centers.append(center)
        face_areas.append(total_area)
        face_normals.append(nrm)

    if tri_list:
        surf_tris = np.vstack(tri_list)
        tri_to_face = np.concatenate(tri_face_list)
        tri_to_part = np.concatenate(tri_part_list)
    else:
        surf_tris = np.zeros((0, 3), dtype=np.int32)
        tri_to_face = np.zeros((0,), dtype=np.int32)
        tri_to_part = np.zeros((0,), dtype=np.int32)

    return TetMesh(
        points=pts,
        tets=np.zeros((0, 4), dtype=np.int32),
        surf_tris=surf_tris,
        tri_to_face=tri_to_face,
        face_centers=np.array(face_centers, dtype=np.float64) if face_centers else np.zeros((0, 3)),
        face_areas=np.array(face_areas, dtype=np.float64) if face_areas else np.zeros((0,)),
        face_normals=np.array(face_normals, dtype=np.float64) if face_normals else np.zeros((0, 3)),
        tet_to_part=np.zeros((0,), dtype=np.int32),
        tri_to_part=tri_to_part,
    )


def make_test_beam(
    length: float = 100.0,
    width: float = 20.0,
    height: float = 10.0,
    name: str = "TestBeam",
) -> Part:
    """Generate a rectangular beam with surface mesh for display.
    
    The full tetrahedral mesh is deferred until :func:`mesh_part` is called.
    """
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 1)  # Delaunay for speed
        gmsh.option.setNumber("Mesh.MeshSizeMin", 2.0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 6.0)
        gmsh.model.add(name)
        gmsh.model.occ.addBox(0.0, -width / 2.0, -height / 2.0, length, width, height)
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)
        mesh = _finalize_mesh_for_display(name)
    finally:
        gmsh.finalize()

    return Part(
        name=name,
        mesh=mesh,
        source="test_beam",
        _beam_params={
            "length": length,
            "width": width,
            "height": height,
        },
    )


def mesh_part(parts: list[Part], mesh_size: float) -> TetMesh:
    """Perform tetrahedral meshing on a list of Parts and return the combined mesh.
    
    The resulting mesh contains all parts with tet_to_part mapping for material
    assignment during FEA.
    """
    if not parts:
        raise ValueError("至少需要一个零件进行网格化")
    
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 1)  # Delaunay for speed
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size * 0.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        
        combined_name = parts[0].name.split("_")[0] if "_" in parts[0].name else parts[0].name
        gmsh.model.add(combined_name)

        first_part = parts[0]
        if first_part._step_path is not None:
            gmsh.merge(str(first_part._step_path))
        elif first_part._beam_params is not None:
            p = first_part._beam_params
            gmsh.model.occ.addBox(0.0, -p["width"] / 2.0, -p["height"] / 2.0,
                                  p["length"], p["width"], p["height"])
            gmsh.model.occ.synchronize()

        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.optimize("Netgen")
        
        mesh = _finalize_mesh(mesh_size, combined_name)
        
        vol_entities = gmsh.model.getEntities(3)
        if len(vol_entities) == len(parts):
            tet_tags, tet_node_tags = gmsh.model.mesh.getElementsByType(4)
            tet_tags = np.asarray(tet_tags, dtype=np.int64)
            for part_idx, (dim, tag) in enumerate(vol_entities):
                try:
                    part_tet_tags = gmsh.model.mesh.getElementsByType(4, tag)
                    part_tet_tags_set = set(part_tet_tags[0])
                    for i, tt in enumerate(tet_tags):
                        if int(tt) in part_tet_tags_set:
                            mesh.tet_to_part[i] = part_idx
                except Exception:
                    continue
        
        return mesh
    finally:
        gmsh.finalize()



