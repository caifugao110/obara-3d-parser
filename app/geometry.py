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


@dataclass
class Part:
    name: str
    mesh: TetMesh
    source: str = ""


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
    tri_list: List[np.ndarray] = []
    tri_face_list: List[int] = []
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
    else:
        surf_tris = np.zeros((0, 3), dtype=np.int32)
        tri_to_face = np.zeros((0,), dtype=np.int32)

    return TetMesh(
        points=pts,
        tets=tets,
        surf_tris=surf_tris,
        tri_to_face=tri_to_face,
        face_centers=np.array(face_centers, dtype=np.float64) if face_centers else np.zeros((0, 3)),
        face_areas=np.array(face_areas, dtype=np.float64) if face_areas else np.zeros((0,)),
        face_normals=np.array(face_normals, dtype=np.float64) if face_normals else np.zeros((0, 3)),
    )


def load_step(path: str | Path, mesh_size: float = 5.0, name: Optional[str] = None) -> Part:
    """Import a STEP file and return a tetrahedral :class:`Part`."""
    path = Path(path)
    if name is None:
        name = path.stem

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size * 0.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.add(name)
        gmsh.merge(str(path))
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.optimize("Netgen")
        mesh = _finalize_mesh(mesh_size, name)
    finally:
        gmsh.finalize()
    return Part(name=name, mesh=mesh, source=str(path))


def make_test_beam(
    length: float = 100.0,
    width: float = 20.0,
    height: float = 10.0,
    mesh_size: float = 6.0,
    name: str = "TestBeam",
) -> Part:
    """Generate a rectangular beam via Gmsh OCC primitives (for validation)."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size * 0.5)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.add(name)
        gmsh.model.occ.addBox(0.0, -width / 2.0, -height / 2.0, length, width, height)
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.optimize("Netgen")
        mesh = _finalize_mesh(mesh_size, name)
    finally:
        gmsh.finalize()
    return Part(name=name, mesh=mesh, source="test_beam")
