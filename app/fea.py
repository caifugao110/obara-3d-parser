"""Linear static FEA solver (SolidWorks Simulation style).

Implements a small-engine linear elasticity solver on linear tetrahedra:

  * Builds the global stiffness matrix for a tetrahedral mesh with a single
    isotropic material (Young's modulus + Poisson's ratio).
  * Applies fixed (zero-displacement) restraints on selected surface faces.
  * Applies normal pressure loads on selected surface faces.
  * Solves K u = f with a sparse direct solver.
  * Post-processes nodal displacements, element von Mises stress (projected
    to nodes for the ISO contour), peak values and a yield-based safety
    factor.
  * Reports the displacement at the loaded face centroid resolved in a
    user-defined coordinate system.

Units are strictly SI internally (metres, Pascals, Newtons). Because STEP
files are conventionally in millimetres, ``solve_static`` accepts a
``length_scale`` (default 1e-3) that converts the mesh coordinates to metres
before analysis. Returned displacements are in metres and stresses in Pa;
the UI converts them to mm / MPa for display.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .geometry import Part, TetMesh
from .material_db import Material


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #
@dataclass
class Fixture:
    """A fixed (zero-displacement) restraint applied to a surface face."""
    face_id: int


@dataclass(init=False)
class PressureLoad:
    """Total normal force distributed over a surface face (N).

    ``pressure`` is accepted as a backward-compatible alias for older tests and
    saved studies, but the value is interpreted as total force in new UI flows.
    Positive values push into the surface, matching SolidWorks' pressure arrow
    convention for normal loads.
    """
    face_id: int
    force: float
    name: str = ""

    def __init__(
        self,
        face_id: int,
        force: Optional[float] = None,
        name: str = "",
        pressure: Optional[float] = None,
    ) -> None:
        if force is None and pressure is None:
            raise TypeError("PressureLoad requires force=... in N")
        self.face_id = face_id
        self.force = float(force if force is not None else pressure)
        self.name = name


@dataclass
class ForceLoad:
    """A concentrated force (N) distributed over a face, along a world axis."""
    face_id: int
    force: float               # N
    direction: Tuple[float, float, float] = (0.0, 0.0, -1.0)
    name: str = ""


@dataclass
class CoordSystem:
    """User-defined analysis coordinate system (right-handed)."""
    origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
    x_axis: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0]))
    y_axis: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0]))

    @property
    def z_axis(self) -> np.ndarray:
        return np.cross(self.x_axis, self.y_axis)

    def rotation_to_local(self) -> np.ndarray:
        """3x3 matrix R such that u_local = R @ u_global (rows = local axes)."""
        x = self.x_axis / (np.linalg.norm(self.x_axis) + 1e-30)
        y = self.y_axis / (np.linalg.norm(self.y_axis) + 1e-30)
        z = np.cross(x, y)
        z = z / (np.linalg.norm(z) + 1e-30)
        y = np.cross(z, x)  # re-orthogonalise
        return np.vstack([x, y, z])


@dataclass
class FEAResult:
    displacements: np.ndarray       # (N,3) nodal displacements (metres, global)
    disp_magnitude: np.ndarray      # (N,)  displacement magnitude (metres)
    von_mises: np.ndarray           # (N,)  nodal von Mises stress (Pa)
    max_displacement: float         # metres
    max_von_mises: float            # Pa
    safety_factor: float
    loaded_face_reports: List[dict] # per loaded face: displacements in user CS
    num_nodes: int
    num_tets: int
    solver_message: str = ""


# --------------------------------------------------------------------------- #
# Geometry helpers (operate on raw arrays, unit-agnostic)
# --------------------------------------------------------------------------- #
def _tet_outward_normals(
    pts: np.ndarray, tets: np.ndarray, tris: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Per surface-triangle outward unit normal and area (robust orientation)."""
    owner: Dict[Tuple[int, int, int], Tuple[int, int]] = {}
    for ti, tet in enumerate(tets):
        tet = [int(v) for v in tet]
        for omit in range(4):
            face = [tet[k] for k in range(4) if k != omit]
            key = tuple(sorted(face))
            owner[key] = (ti, tet[omit])

    normals = np.zeros((len(tris), 3), dtype=np.float64)
    areas = np.zeros(len(tris), dtype=np.float64)
    for i, tri in enumerate(tris):
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        p0, p1, p2 = pts[a], pts[b], pts[c]
        n = np.cross(p1 - p0, p2 - p0)
        area = 0.5 * np.linalg.norm(n)
        areas[i] = area
        if area < 1e-18:
            normals[i] = np.array([0.0, 0.0, 1.0])
            continue
        key = tuple(sorted([a, b, c]))
        if key in owner:
            ti, opp = owner[key]
            opp_pt = pts[opp]
            centroid = (p0 + p1 + p2) / 3.0
            if np.dot(centroid - opp_pt, n) < 0:
                n = -n
        normals[i] = n / (np.linalg.norm(n) + 1e-30)
    return normals, areas


def _lame_parameters(E: float, nu: float) -> Tuple[float, float]:
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    return lam, mu


# --------------------------------------------------------------------------- #
# Stiffness assembly (linear elasticity, hand-written B-matrix)
# --------------------------------------------------------------------------- #
def _assemble_stiffness(
    pts: np.ndarray, tets: np.ndarray, tet_to_part: np.ndarray,
    materials: List['Material'],
) -> sp.csc_matrix:
    """Assemble the global stiffness matrix K (3N x 3N) with multi-material support.

    DOF ordering is component-major: [ux(0..N-1), uy(0..N-1), uz(0..N-1)].
    Each part can have a different material, mapped via tet_to_part.
    """
    n_nodes = pts.shape[0]
    n_tets = tets.shape[0]
    ndof = 3 * n_nodes

    p = pts[tets]                                  # (M,4,3)
    p0 = p[:, 0, :]
    J = np.stack([p[:, 1, :] - p0, p[:, 2, :] - p0, p[:, 3, :] - p0], axis=2)
    vol = np.abs(np.linalg.det(J)) / 6.0
    Jinv = np.linalg.inv(J)

    dN_dxi = np.array([
        [-1.0, -1.0, -1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    dN_dx = np.einsum('ij,mjk->mik', dN_dxi, Jinv)   # (M,4,3)
    dNx, dNy, dNz = dN_dx[:, :, 0], dN_dx[:, :, 1], dN_dx[:, :, 2]

    M = n_tets
    B = np.zeros((M, 6, 12))
    for a in range(4):
        B[:, 0, 3 * a + 0] = dNx[:, a]
        B[:, 1, 3 * a + 1] = dNy[:, a]
        B[:, 2, 3 * a + 2] = dNz[:, a]
        B[:, 3, 3 * a + 0] = dNy[:, a]
        B[:, 3, 3 * a + 1] = dNx[:, a]
        B[:, 4, 3 * a + 1] = dNz[:, a]
        B[:, 4, 3 * a + 2] = dNy[:, a]
        B[:, 5, 3 * a + 0] = dNz[:, a]
        B[:, 5, 3 * a + 2] = dNx[:, a]

    part_lame_params = []
    for mat in materials:
        if mat is not None:
            part_lame_params.append(_lame_parameters(mat.ex, mat.nuxy))
        else:
            part_lame_params.append((0.0, 0.0))

    gdof = np.empty((M, 12), dtype=np.int64)
    for a in range(4):
        gdof[:, 3 * a + 0] = tets[:, a] + 0 * n_nodes
        gdof[:, 3 * a + 1] = tets[:, a] + 1 * n_nodes
        gdof[:, 3 * a + 2] = tets[:, a] + 2 * n_nodes

    K = sp.lil_matrix((ndof, ndof))

    for part_idx, (lam, mu) in enumerate(part_lame_params):
        if lam == 0 and mu == 0:
            continue
        part_mask = tet_to_part == part_idx
        if not np.any(part_mask):
            continue
        
        part_tets = tets[part_mask]
        part_vol = vol[part_mask]
        part_B = B[part_mask]
        
        D = np.array([
            [lam + 2 * mu, lam, lam, 0, 0, 0],
            [lam, lam + 2 * mu, lam, 0, 0, 0],
            [lam, lam, lam + 2 * mu, 0, 0, 0],
            [0, 0, 0, 2 * mu, 0, 0],
            [0, 0, 0, 0, 2 * mu, 0],
            [0, 0, 0, 0, 0, 2 * mu],
        ])
        
        part_DB = np.einsum('ij,mjk->mik', D, part_B)
        part_Ke = np.einsum('mji,mjk->mik', part_B, part_DB)
        part_Ke *= part_vol[:, None, None]
        
        part_gdof = np.empty((len(part_tets), 12), dtype=np.int64)
        n_nodes_local = n_nodes
        for a in range(4):
            part_gdof[:, 3 * a + 0] = part_tets[:, a] + 0 * n_nodes_local
            part_gdof[:, 3 * a + 1] = part_tets[:, a] + 1 * n_nodes_local
            part_gdof[:, 3 * a + 2] = part_tets[:, a] + 2 * n_nodes_local
        
        for i in range(len(part_tets)):
            ke = part_Ke[i]
            dofs = part_gdof[i]
            for r in range(12):
                for c in range(12):
                    K[dofs[r], dofs[c]] += ke[r, c]

    return K.tocsc()


# --------------------------------------------------------------------------- #
# Load vector assembly
# --------------------------------------------------------------------------- #
def _assemble_loads(
    mesh: TetMesh,
    pressure_loads: List[PressureLoad],
    force_loads: List[ForceLoad],
    tri_normals: np.ndarray,
    tri_areas: np.ndarray,
) -> np.ndarray:
    n_nodes = mesh.num_nodes
    f = np.zeros((3, n_nodes))

    for load in pressure_loads:
        tris_idx = np.where(mesh.tri_to_face == load.face_id)[0]
        if len(tris_idx) == 0:
            continue
        
        total_area = tri_areas[tris_idx].sum()
        if total_area < 1e-18:
            continue
        
        for ti in tris_idx:
            tri = mesh.surf_tris[ti]
            n = tri_normals[ti]
            a = tri_areas[ti]
            tri_force = -load.force * n * (a / total_area)
            node_force = tri_force / 3.0
            for node in tri:
                f[:, int(node)] += node_force

    for load in force_loads:
        tris_idx = np.where(mesh.tri_to_face == load.face_id)[0]
        if len(tris_idx) == 0:
            continue
        
        total_area = tri_areas[tris_idx].sum()
        if total_area < 1e-18:
            continue
        
        dirv = np.asarray(load.direction, dtype=np.float64)
        dirv = dirv / (np.linalg.norm(dirv) + 1e-30)
        
        for ti in tris_idx:
            tri = mesh.surf_tris[ti]
            a = tri_areas[ti]
            tri_force = load.force * dirv * (a / total_area)
            node_force = tri_force / 3.0
            for node in tri:
                f[:, int(node)] += node_force

    return f.reshape(-1)


# --------------------------------------------------------------------------- #
# Stress recovery
# --------------------------------------------------------------------------- #
def _recover_stress(
    pts: np.ndarray, tets: np.ndarray, tet_to_part: np.ndarray,
    u: np.ndarray, materials: List['Material'],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return (nodal von Mises, element von Mises) in Pa with multi-material support."""
    n_nodes = pts.shape[0]
    U = u.reshape(3, n_nodes)                  # component-major

    p = pts[tets]
    p0 = p[:, 0, :]
    J = np.stack([p[:, 1, :] - p0, p[:, 2, :] - p0, p[:, 3, :] - p0], axis=2)
    vol = np.abs(np.linalg.det(J)) / 6.0
    Jinv = np.linalg.inv(J)
    dN_dxi = np.array([
        [-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
    ])
    dN_dx = np.einsum('ij,mjk->mik', dN_dxi, Jinv)   # (M,4,3)

    u_elem = np.transpose(U[:, tets], (1, 0, 2))      # (M,3,4)
    grad_u = np.einsum('mka,maj->mkj', u_elem, dN_dx)  # (M,3,3)
    eps = 0.5 * (grad_u + grad_u.transpose(0, 2, 1))

    exx = eps[:, 0, 0]; eyy = eps[:, 1, 1]; ezz = eps[:, 2, 2]
    exy = eps[:, 0, 1]; eyz = eps[:, 1, 2]; ezx = eps[:, 0, 2]
    tr = exx + eyy + ezz

    part_lame_params = []
    for mat in materials:
        if mat is not None:
            part_lame_params.append(_lame_parameters(mat.ex, mat.nuxy))
        else:
            part_lame_params.append((0.0, 0.0))
    
    vm = np.zeros(len(tets), dtype=np.float64)
    
    for part_idx, (lam, mu) in enumerate(part_lame_params):
        if lam == 0 and mu == 0:
            continue
        part_mask = tet_to_part == part_idx
        if not np.any(part_mask):
            continue
        
        sxx_p = 2 * mu * exx[part_mask] + lam * tr[part_mask]
        syy_p = 2 * mu * eyy[part_mask] + lam * tr[part_mask]
        szz_p = 2 * mu * ezz[part_mask] + lam * tr[part_mask]
        sxy_p = 2 * mu * exy[part_mask]
        syz_p = 2 * mu * eyz[part_mask]
        szx_p = 2 * mu * ezx[part_mask]
        vm[part_mask] = np.sqrt(0.5 * (
            (sxx_p - syy_p) ** 2 + (syy_p - szz_p) ** 2 + (szz_p - sxx_p) ** 2
            + 6.0 * (sxy_p ** 2 + syz_p ** 2 + szx_p ** 2)
        ))

    nodal = np.zeros(n_nodes)
    weight = np.zeros(n_nodes)
    for a in range(4):
        np.add.at(nodal, tets[:, a], vm * vol)
        np.add.at(weight, tets[:, a], vol)
    nodal = nodal / np.where(weight > 0, weight, 1.0)
    return nodal, vm


# --------------------------------------------------------------------------- #
# Public solve API
# --------------------------------------------------------------------------- #
def solve_static(
    parts: List[Part],
    fixtures: List[Fixture],
    loads: List[object],
    coord_system: Optional[CoordSystem] = None,
    progress: Optional[Callable[[str], None]] = None,
    length_scale: float = 1e-3,
) -> FEAResult:
    """Run a linear static study with multi-material support.

    ``length_scale`` converts the mesh coordinates to metres (default 1e-3,
    i.e. the STEP file is assumed to be in millimetres). All material
    properties from the database are SI (Pa), so analysis is fully SI.
    
    Each part in the parts list can have its own material defined.
    """
    if progress is None:
        progress = lambda s: None
    
    if not parts:
        raise ValueError("至少需要一个零件进行分析")
    
    for i, p in enumerate(parts):
        if p.material is None:
            raise ValueError(f"零件 {i+1} ({p.name}) 尚未定义材质")
        mat = p.material
        if mat.ex <= 0:
            raise ValueError(f"零件 {i+1} ({p.name}) 的弹性模量 EX 无效，请检查材质定义。")
        if not (0.0 <= mat.nuxy < 0.5):
            raise ValueError(f"零件 {i+1} ({p.name}) 的泊松比 NUXY 必须在 [0, 0.5) 之间。")

    mesh = parts[0].mesh
    if mesh is None:
        raise ValueError("零件尚未网格化")
    
    pts_si = mesh.points.astype(np.float64) * length_scale
    tets = mesh.tets.astype(np.int64)
    tet_to_part = mesh.tet_to_part.astype(np.int64)
    n_nodes = pts_si.shape[0]
    ndof = 3 * n_nodes

    materials = [p.material for p in parts]

    progress("正在装配刚度矩阵…")
    K = _assemble_stiffness(pts_si, tets, tet_to_part, materials)

    progress("正在计算面法向与面积…")
    tri_normals, tri_areas = _tet_outward_normals(
        pts_si, tets, mesh.surf_tris,
    )

    progress("正在装配载荷向量…")
    pressure_loads = [l for l in loads if isinstance(l, PressureLoad)]
    force_loads = [l for l in loads if isinstance(l, ForceLoad)]
    f = _assemble_loads(mesh, pressure_loads, force_loads, tri_normals, tri_areas)

    # fixed DOFs: all 3 components of every node on a fixed face
    fixed_nodes = set()
    for fix in fixtures:
        tris_idx = np.where(mesh.tri_to_face == fix.face_id)[0]
        if len(tris_idx) == 0:
            continue
        fixed_nodes.update(mesh.surf_tris[tris_idx].ravel().tolist())

    free = np.ones(ndof, dtype=bool)
    for n in fixed_nodes:
        free[n + 0 * n_nodes] = False
        free[n + 1 * n_nodes] = False
        free[n + 2 * n_nodes] = False
    free_idx = np.where(free)[0]
    if len(free_idx) == 0:
        raise ValueError("所有自由度均被约束，无法求解。")

    progress("正在求解线性方程组…")
    Kff = K[free_idx][:, free_idx]
    u = np.zeros(ndof)
    u[free_idx] = spla.spsolve(Kff.tocsc(), f[free_idx])

    progress("正在恢复应力…")
    U = u.reshape(3, n_nodes).T            # (N,3) nodal displacements, metres
    disp_mag = np.linalg.norm(U, axis=1)
    nodal_vm, elem_vm = _recover_stress(pts_si, tets, tet_to_part, u, materials)

    max_disp = float(disp_mag.max())
    max_vm = float(nodal_vm.max())
    min_sigyld = min(p.material.sigyld for p in parts if p.material and p.material.sigyld > 0)
    safety = float(min_sigyld / max_vm) if (max_vm > 0 and min_sigyld > 0) else float("inf")

    cs = coord_system or CoordSystem()
    R = cs.rotation_to_local()
    reports: List[dict] = []
    for load in pressure_loads + force_loads:  # type: ignore
        face_id = load.face_id
        tris_idx = np.where(mesh.tri_to_face == face_id)[0]
        if len(tris_idx) == 0:
            continue
        face_nodes = np.unique(mesh.surf_tris[tris_idx].ravel())
        u_face = U[face_nodes].mean(axis=0)
        u_local = R @ u_face
        centroid = (mesh.face_centers[face_id] * length_scale
                    if face_id < len(mesh.face_centers) else np.zeros(3))
        reports.append({
            "name": getattr(load, "name", "") or f"面 {face_id}",
            "face_id": face_id,
            "centroid_global": centroid.tolist(),
            "disp_global": u_face.tolist(),
            "disp_local": u_local.tolist(),
            "magnitude": float(np.linalg.norm(u_face)),
            "load_type": "pressure" if isinstance(load, PressureLoad) else "force",
            "load_value": load.force if isinstance(load, PressureLoad) else load.force,
        })

    progress("完成。")
    return FEAResult(
        displacements=U,
        disp_magnitude=disp_mag,
        von_mises=nodal_vm,
        max_displacement=max_disp,
        max_von_mises=max_vm,
        safety_factor=safety,
        loaded_face_reports=reports,
        num_nodes=n_nodes,
        num_tets=mesh.num_tets,
    )
