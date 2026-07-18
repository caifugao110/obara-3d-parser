from pathlib import Path

import numpy as np

from app.solver_backends import (
    _read_calculix_dat_displacements,
    _read_calculix_frd_displacements,
)


def test_read_calculix_dat_displacements(tmp_path: Path):
    dat_path = tmp_path / "study.dat"
    dat_path.write_text(
        """
        displacements (vx,vy,vz) for set ALLNODES

             1  1.000000E-03  2.000000E-03  3.000000E-03
             2 -1.000000D-03  0.000000E+00  4.000000E-03
        """,
        encoding="utf-8",
    )

    displacements = _read_calculix_dat_displacements(dat_path, 2)

    assert displacements is not None
    np.testing.assert_allclose(
        displacements,
        np.array([[1e-3, 2e-3, 3e-3], [-1e-3, 0.0, 4e-3]]),
    )


def test_read_calculix_frd_displacements(tmp_path: Path):
    frd_path = tmp_path / "study.frd"
    frd_path.write_text(
        """
 100CL  101
 -4  DISP        4    1
 -5  D1          1    2    1    0
 -5  D2          1    2    2    0
 -5  D3          1    2    3    0
 -1         1  1.000000E-03  2.000000E-03  3.000000E-03
 -1         2 -1.000000E-03  0.000000E+00  4.000000E-03
 -3
        """,
        encoding="utf-8",
    )

    displacements = _read_calculix_frd_displacements(frd_path, 2)

    assert displacements is not None
    np.testing.assert_allclose(
        displacements,
        np.array([[1e-3, 2e-3, 3e-3], [-1e-3, 0.0, 4e-3]]),
    )
