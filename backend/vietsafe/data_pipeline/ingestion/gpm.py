"""GPM precipitation-rate interchange boundary; no native HDF5/NetCDF decoding."""

from .environment_json import grid_cli, read_grid


def read_gpm(path):
    return read_grid(path, "gpm")


def main(argv=None):
    grid_cli(read_gpm, "Offline GPM normalized JSON (not native NASA granules)", argv)


if __name__ == "__main__":
    main()
